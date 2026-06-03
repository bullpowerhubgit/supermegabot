// ============================================================
// server.js — AutoPilot Business Bot · Express Server
// Rudolf Sarkany · Port 3200 · Production Ready
// ============================================================
'use strict';
require('dotenv').config();

const express      = require('express');
const cors         = require('cors');
const helmet       = require('helmet');
const rateLimit    = require('express-rate-limit');
const crypto       = require('crypto');
const fs           = require('fs');
const path         = require('path');

// Import core components
const { Orchestrator } = require('./core/orchestrator');
const { AppContext } = require('./core/app-context');
const { registerHealthRoutes } = require('./routes/health');
const { registerJobRoutes } = require('./routes/jobs');
const { registerApprovalRoutes } = require('./routes/approvals');
const agentHelpRoutes = require('./api/agent-help');

// ── ENV validation ───────────────────────────────────────────
// No required keys for basic functionality
const REQUIRED_KEYS = [];
const missing = REQUIRED_KEYS.filter(k => !process.env[k] || process.env[k].includes('PLACEHOLDER'));
if (missing.length) {
  console.error(`❌ Fehlende oder Platzhalter ENV Keys: ${missing.join(', ')}`);
  process.exit(1);
}

// Optional APIs - silently continue if not configured
const OPTIONAL_KEYS = ['SHOPIFY_STORE_URL','SHOPIFY_ADMIN_TOKEN','TELEGRAM_BOT_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY','PERPLEXITY_API_KEY','GITHUB_TOKEN','SENDGRID_API_KEY','STRIPE_API_KEY','DIGISTORE_API_KEY'];
// Don't log warnings in production to avoid crashes

const PORT    = process.env.PORT || 3200;
const SHOP    = process.env.SHOPIFY_STORE_URL;
const TOK     = process.env.SHOPIFY_ADMIN_TOKEN;
const GH_TOK  = process.env.GITHUB_TOKEN;
const GH_USER = process.env.GITHUB_USERNAME || 'bullpowerhubgit';
const API_VER = process.env.SHOPIFY_API_VERSION || '2025-01';

const app = express();
const startTime = Date.now();

// ── Logs dir ─────────────────────────────────────────────────
try {
  ['logs'].forEach(d => !fs.existsSync(d) && fs.mkdirSync(d, { recursive: true }));
} catch (e) {
  // Read-only filesystem (e.g. Vercel) — skip
}

// ── Security Middleware ───────────────────────────────────────
// Enable Content Security Policy with secure defaults
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'", "https://api.telegram.org", "https://api.shopify.com"]
    }
  }
}));

// Restrict CORS origins for security
const allowedOrigins = [
  'http://localhost:3000',
  'http://localhost:3200',
  'https://vercel.app',
  'https://rudibot.vercel.app',
  process.env.FRONTEND_URL
].filter(Boolean);

app.use(cors({ 
  origin: function (origin, callback) {
    // Allow requests with no origin (mobile apps, curl, etc.)
    if (!origin) return callback(null, true);
    
    if (allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      console.warn(`CORS blocked origin: ${origin}`);
      callback(new Error('Not allowed by CORS'));
    }
  },
  methods: ['GET','POST','PUT','DELETE','OPTIONS'],
  credentials: true
}));

app.use(express.json({ limit: '5mb' }));
app.use(express.urlencoded({ extended: true }));

// Rate limiting - reduced for better security
const limiter = rateLimit({ windowMs: 60*1000, max: 60, standardHeaders: true, legacyHeaders: false, message: { error: 'Rate limit exceeded — 60 req/min' } });
const aiLimiter = rateLimit({ windowMs: 60*1000, max: 30, message: { error: 'AI Rate limit — 30 req/min' } });
app.use('/api/', limiter);
app.use('/api/ai/', aiLimiter);

// ── Request Logger ────────────────────────────────────────────
app.use((req, _, next) => {
  const ts = new Date().toISOString().slice(11,19);
  console.log(`[${ts}] ${req.method} ${req.path}`);
  next();
});

// ── INITIALIZATION ─────────────────────────────────────────────
// Create app context
const context = new AppContext({
  logger: console
});

// Initialize orchestrator
const orchestrator = new Orchestrator({
  logger: console,
  context: context,
  telegramBot: null // TODO: Add telegram bot integration
});

// Initialize modules
const CommerceModule = require('./modules/commerce/index');
const FinanceModule = require('./modules/finance/index');
const SecurityModule = require('./modules/security/index');
const LegalTaxModule = require('./modules/legal_tax/index');
const OrchestratorModule = require('./modules/orchestrator/index');

const commerceModule = new CommerceModule(orchestrator);
const financeModule = new FinanceModule(orchestrator);
const securityModule = new SecurityModule(orchestrator);
const legalTaxModule = new LegalTaxModule(orchestrator);
const orchestratorModule = new OrchestratorModule(orchestrator);

// Initialize KIVO Layer
const KIVOLayer = require('./core/kivo');
const kivo = new KIVOLayer({
  logger: console,
  orchestrator: orchestrator,
  context: context,
  llmConfig: {
    provider: 'openai',
    apiKey: process.env.OPENAI_API_KEY
  }
});

// Register routes
registerHealthRoutes(app, { context, scheduler: orchestrator });
registerJobRoutes(app, { scheduler: orchestrator });
registerApprovalRoutes(app, { context });

// Mount agent help routes for other agents
app.use('/api/agent-help', agentHelpRoutes);

// Start orchestrator
orchestrator.start().catch(console.error);

// Mount orchestrator routes
app.use('/orchestrator', orchestrator.getRouter());

// Mount dashboard routes
app.use('/dashboard', orchestrator.getDashboardRouter());

// Serve static dashboard UI
app.use(express.static(path.join(__dirname, '../public')));
app.get('/ui', (_, res) => {
  res.sendFile(path.join(__dirname, '../public/dashboard.html'));
});
app.get('/orchestrator-ui', (_, res) => {
  res.sendFile(path.join(__dirname, '../public/orchestrator-dashboard.html'));
});
app.get('/revenue-first', (_, res) => {
  res.sendFile(path.join(__dirname, '../public/revenue-first-dashboard.html'));
});
app.get('/finanz-assistant', (_, res) => {
  res.sendFile(path.join(__dirname, '../public/finanz-assistant-dashboard.html'));
});

// ── HELPERS ───────────────────────────────────────────────────
async function shopifyFetch(endpoint, opts = {}, store = SHOP, token = TOK) {
  const url = `https://${store}/admin/api/${API_VER}/${endpoint}`;
  const res = await fetch(url, {
    ...opts,
    headers: { 'X-Shopify-Access-Token': token, 'Content-Type': 'application/json', ...(opts.headers||{}) }
  });
  if (!res.ok) throw new Error(`Shopify ${res.status}: ${await res.text()}`);
  return res.json();
}

async function githubFetch(endpoint, opts = {}) {
  const res = await fetch(`https://api.github.com/${endpoint}`, {
    ...opts,
    headers: { 'Authorization': `token ${GH_TOK}`, 'Accept': 'application/vnd.github.v3+json', ...(opts.headers||{}) }
  });
  if (!res.ok) throw new Error(`GitHub ${res.status}: ${await res.text()}`);
  return res.json();
}

async function claudeFetch(prompt, system = '', maxTokens = 1024) {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({ model: 'claude-sonnet-4-20250514', max_tokens: maxTokens, system, messages: [{ role: 'user', content: prompt }] })
  });
  if (!res.ok) throw new Error(`Claude API ${res.status}`);
  const d = await res.json();
  return d.content?.[0]?.text || '';
}

// ── ════════════════════════════════════════════════════════ ──
// ── API ROUTES                                               ──
// ── ════════════════════════════════════════════════════════ ──

// ── WEBHOOK ENDPOINT ───────────────────────────────────────────
app.post('/webhook', express.raw({ type: 'application/json' }), (req, res) => {
  try {
    const webhookData = JSON.parse(req.body);
    console.log('🔔 Webhook received:', {
      timestamp: new Date().toISOString(),
      topic: req.headers['x-shopify-topic'] || 'unknown',
      shop: req.headers['x-shopify-shop-domain'] || 'unknown',
      data: webhookData
    });

    // Process webhook based on topic
    const topic = req.headers['x-shopify-topic'];
    switch (topic) {
      case 'orders/create':
        console.log('📦 New order created:', webhookData.id);
        break;
      case 'app/uninstalled':
        console.log('🚫 App uninstalled');
        break;
      case 'customer/create':
        console.log('👤 New customer created:', webhookData.id);
        break;
      default:
        console.log('📋 Generic webhook processed');
    }

    res.status(200).send('OK');
  } catch (error) {
    console.error('❌ Webhook processing error:', error.message);
    res.status(400).json({ error: 'Invalid webhook data' });
  }
});

// ── HEALTH ───────────────────────────────────────────────────
app.get('/api/health', async (req, res) => {
  const uptime = Math.round((Date.now() - startTime) / 1000);
  const checks = {
    server: 'ok',
    uptime: `${uptime}s`,
    memory: `${Math.round(process.memoryUsage().heapUsed / 1024 / 1024)}MB`,
    node: process.version,
    env: {
      anthropic:  !!process.env.ANTHROPIC_API_KEY,
      telegram:   !!process.env.TELEGRAM_BOT_TOKEN,
      shopify1:   !!TOK,
      github:     !!GH_TOK,
      openai:     !!process.env.OPENAI_API_KEY,
      perplexity: !!process.env.PERPLEXITY_API_KEY,
    }
  };
  const allOk = Object.values(checks.env).every(Boolean);
  res.status(allOk ? 200 : 206).json({ status: allOk ? 'ok' : 'degraded', ...checks, timestamp: new Date().toISOString() });
});

app.get('/',        (_, res) => res.json({ name: 'AutoPilot Business Bot', version: '1.0.0', status: 'running', port: PORT }));
app.get('/api/status', (_, res) => res.json({ name: 'AutoPilot Business Bot', version: '1.0.0', status: 'running', port: PORT }));
app.get('/health',  (_, res) => res.redirect('/api/health'));

// ── SHOPIFY — Store 1 ─────────────────────────────────────────
app.get('/api/shopify/store', async (_, res) => {
  try { res.json(await shopifyFetch('shop.json')); }
  catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/shopify/products', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit)||20, 250);
    res.json(await shopifyFetch(`products.json?limit=${limit}`));
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/shopify/orders', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit)||20, 250);
    const status = req.query.status || 'any';
    res.json(await shopifyFetch(`orders.json?limit=${limit}&status=${status}`));
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/shopify/customers', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit)||20, 250);
    res.json(await shopifyFetch(`customers.json?limit=${limit}`));
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/shopify/inventory', async (req, res) => {
  try { res.json(await shopifyFetch('inventory_levels.json?limit=50')); }
  catch(e) { res.status(500).json({ error: e.message }); }
});

// Shopify GraphQL Proxy
app.post('/api/shopify/graphql', async (req, res) => {
  try {
    const r = await fetch(`https://${SHOP}/admin/api/${API_VER}/graphql.json`, {
      method: 'POST',
      headers: { 'X-Shopify-Access-Token': TOK, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: req.body.query, variables: req.body.variables })
    });
    res.json(await r.json());
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── SHOPIFY WEBHOOKS ──────────────────────────────────────────
function verifyWebhook(rawBody, hmac) {
  const secret = process.env.SHOPIFY_WEBHOOK_SECRET || '';
  if (!secret) {
    // In production, require webhook secret for security
    if (process.env.NODE_ENV === 'production') {
      console.error('❌ SHOPIFY_WEBHOOK_SECRET required in production');
      return false;
    }
    // Development mode - allow but log warning
    console.warn('⚠️ SHOPIFY_WEBHOOK_SECRET not configured - allowing webhooks in dev mode only');
    return true;
  }
  const hash = crypto.createHmac('sha256', secret).update(rawBody, 'utf8').digest('base64');
  return crypto.timingSafeEqual(Buffer.from(hash), Buffer.from(hmac || '', 'base64'));
}

app.post('/webhooks/shopify/:event', express.raw({ type: 'application/json' }), (req, res) => {
  const hmac = req.headers['x-shopify-hmac-sha256'];
  if (!verifyWebhook(req.body, hmac)) return res.status(401).json({ error: 'Unauthorized' });

  const event   = req.params.event;
  const payload = JSON.parse(req.body.toString());
  console.log(`📦 Shopify Webhook: ${event}`, JSON.stringify(payload).slice(0,200));

  // Async processing
  setImmediate(async () => {
    try {
      if (event === 'orders-create' || event === 'orders-paid') {
        // Neue Bestellung → Bot benachrichtigen
        console.log(`🛒 Neue Bestellung #${payload.order_number} · €${payload.total_price}`);
      }
      if (event === 'products-create') {
        console.log(`📦 Neues Produkt: ${payload.title}`);
      }
    } catch(err) { console.error('Webhook processing error:', err); }
  });

  res.status(200).json({ received: true });
});

// ── GITHUB ────────────────────────────────────────────────────
app.get('/api/github/repos', async (req, res) => {
  if (!GH_TOK) return res.status(503).json({ error: 'GITHUB_TOKEN nicht konfiguriert' });
  try {
    const sort = req.query.sort || 'updated';
    const data = await githubFetch(`users/${GH_USER}/repos?per_page=30&sort=${sort}`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/github/repos/:name', async (req, res) => {
  try { res.json(await githubFetch(`repos/${GH_USER}/${req.params.name}`)); }
  catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/github/repos', async (req, res) => {
  try {
    const data = await githubFetch('user/repos', {
      method: 'POST',
      body: JSON.stringify({ name: req.body.name, private: req.body.private ?? true, auto_init: true, description: req.body.description })
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/github/repos/:name/files/*', async (req, res) => {
  try {
    const filePath = req.params[0];
    const branch   = req.query.branch || 'main';
    res.json(await githubFetch(`repos/${GH_USER}/${req.params.name}/contents/${filePath}?ref=${branch}`));
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── CLAUDE AI ─────────────────────────────────────────────────
app.post('/api/ai/claude', async (req, res) => {
  try {
    const { prompt, system = '', max_tokens = 1024 } = req.body;
    if (!prompt) return res.status(400).json({ error: 'prompt required' });
    const text = await claudeFetch(prompt, system, max_tokens);
    res.json({ text, model: 'claude-sonnet-4-20250514' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Proxy für Artifacts (ohne eigenen API Key)
app.post('/api/ai/proxy', async (req, res) => {
  try {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify(req.body)
    });
    const data = await r.json();
    res.status(r.status).json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── OPENAI ───────────────────────────────────────────────────
app.post('/api/ai/openai', async (req, res) => {
  const key = process.env.OPENAI_API_KEY;
  if (!key) return res.status(503).json({ error: 'OPENAI_API_KEY nicht konfiguriert' });
  try {
    const { prompt, model = 'gpt-4o-mini', max_tokens = 1024 } = req.body;
    if (!prompt) return res.status(400).json({ error: 'prompt required' });
    const r = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }], max_tokens })
    });
    const data = await r.json();
    if (r.ok) {
      res.json({ text: data.choices?.[0]?.message?.content || '', model });
    } else {
      res.status(r.status).json({ error: data.error?.message || 'OpenAI API Error' });
    }
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── PERPLEXITY ────────────────────────────────────────────────
app.post('/api/ai/perplexity', async (req, res) => {
  const key = process.env.PERPLEXITY_API_KEY;
  if (!key) return res.status(503).json({ error: 'PERPLEXITY_API_KEY nicht konfiguriert' });
  try {
    const { query, model = 'sonar-pro' } = req.body;
    const r = await fetch('https://api.perplexity.ai/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, messages: [{ role: 'user', content: query }] })
    });
    res.json(await r.json());
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── TELEGRAM ──────────────────────────────────────────────────
app.get('/api/telegram/status', async (req, res) => {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token || token.includes('PLACEHOLDER')) return res.status(503).json({ error: 'TELEGRAM_BOT_TOKEN nicht konfiguriert' });
  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/getMe`);
    const data = await r.json();
    if (data.ok) res.json({ ok: true, bot: data.result });
    else res.status(502).json({ error: data.description || 'Telegram API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/telegram/send', async (req, res) => {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token || token.includes('PLACEHOLDER')) return res.status(503).json({ error: 'TELEGRAM_BOT_TOKEN nicht konfiguriert' });
  try {
    const { chat_id, text } = req.body;
    if (!chat_id || !text) return res.status(400).json({ error: 'chat_id und text required' });
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id, text })
    });
    const data = await r.json();
    res.status(r.ok && data.ok ? 200 : 502).json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── EMAIL (SendGrid) ────────────────────────────────────────────
app.post('/api/email/send', async (req, res) => {
  const key = process.env.SENDGRID_API_KEY;
  if (!key) return res.status(503).json({ error: 'SENDGRID_API_KEY nicht konfiguriert' });
  try {
    const { to, subject, html, text } = req.body;
    const r = await fetch('https://api.sendgrid.com/v3/mail/send', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: to }] }],
        from: { email: process.env.EMAIL_FROM || 'noreply@yourdomain.com' },
        subject,
        content: [{ type: html ? 'text/html' : 'text/plain', value: html || text }]
      })
    });
    if (r.status === 202) {
      res.json({ success: true, message: 'Email sent successfully' });
    } else {
      const error = await r.text();
      res.status(r.status).json({ error: error });
    }
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── SUPABASE ────────────────────────────────────────────────────
async function supabaseFetch(endpoint, opts = {}) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/${endpoint}`;
  const res = await fetch(url, {
    ...opts,
    headers: { 
      'apikey': process.env.SUPABASE_ANON_KEY, 
      'Authorization': `Bearer ${process.env.SUPABASE_ANON_KEY}`,
      'Content-Type': 'application/json',
      ...(opts.headers||{}) 
    }
  });
  if (!res.ok) throw new Error(`Supabase ${res.status}: ${await res.text()}`);
  return res.json();
}

app.get('/api/supabase/:table', async (req, res) => {
  const key = process.env.SUPABASE_ANON_KEY;
  if (!key) return res.status(503).json({ error: 'SUPABASE_ANON_KEY nicht konfiguriert' });
  try {
    const table = req.params.table;
    
    // SECURITY: Whitelist allowed table names to prevent SQL injection
    const allowedTables = [
      'users', 'products', 'orders', 'customers', 'analytics', 
      'settings', 'logs', 'campaigns', 'revenue', 'expenses'
    ];
    
    if (!allowedTables.includes(table)) {
      return res.status(400).json({ 
        error: 'Invalid table name',
        allowedTables: allowedTables 
      });
    }
    
    const limit = Math.min(parseInt(req.query.limit)||20, 100);
    const data = await supabaseFetch(`${table}?limit=${limit}`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/supabase/:table', async (req, res) => {
  const key = process.env.SUPABASE_ANON_KEY;
  if (!key) return res.status(503).json({ error: 'SUPABASE_ANON_KEY nicht konfiguriert' });
  try {
    const table = req.params.table;
    const data = await supabaseFetch(table, {
      method: 'POST',
      body: JSON.stringify(req.body)
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── PRINTIFY ────────────────────────────────────────────────────
async function printifyFetch(endpoint, opts = {}) {
  const url = `https://api.printify.com/v1/${endpoint}`;
  const res = await fetch(url, {
    ...opts,
    headers: { 'Authorization': `Bearer ${process.env.PRINTIFY_API_KEY}`, 'Content-Type': 'application/json', ...(opts.headers||{}) }
  });
  if (!res.ok) throw new Error(`Printify ${res.status}: ${await res.text()}`);
  return res.json();
}

app.get('/api/printify/shops', async (req, res) => {
  const key = process.env.PRINTIFY_API_KEY;
  if (!key) return res.status(503).json({ error: 'PRINTIFY_API_KEY nicht konfiguriert' });
  try {
    const data = await printifyFetch('shops');
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/printify/products', async (req, res) => {
  const key = process.env.PRINTIFY_API_KEY;
  const shopId = process.env.PRINTIFY_SHOP_ID;
  if (!key || !shopId) return res.status(503).json({ error: 'PRINTIFY_API_KEY oder PRINTIFY_SHOP_ID nicht konfiguriert' });
  try {
    const data = await printifyFetch(`shops/${shopId}/products`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/printify/products', async (req, res) => {
  const key = process.env.PRINTIFY_API_KEY;
  const shopId = process.env.PRINTIFY_SHOP_ID;
  if (!key || !shopId) return res.status(503).json({ error: 'PRINTIFY_API_KEY oder PRINTIFY_SHOP_ID nicht konfiguriert' });
  try {
    const data = await printifyFetch(`shops/${shopId}/products`, {
      method: 'POST',
      body: JSON.stringify(req.body)
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── YOUTUBE ────────────────────────────────────────────────────
app.get('/api/youtube/channel', async (req, res) => {
  const key = process.env.YOUTUBE_API_KEY;
  const channelId = process.env.YOUTUBE_CHANNEL_ID;
  if (!key) return res.status(503).json({ error: 'YOUTUBE_API_KEY nicht konfiguriert' });
  try {
    const url = `https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id=${channelId}&key=${key}`;
    const r = await fetch(url);
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error?.message || 'YouTube API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── KLAVIYO ────────────────────────────────────────────────────
app.get('/api/klaviyo/profiles', async (req, res) => {
  const key = process.env.KLAVIYO_API_KEY;
  if (!key) return res.status(503).json({ error: 'KLAVIYO_API_KEY nicht konfiguriert' });
  try {
    const r = await fetch('https://a.klaviyo.com/api/profiles/', {
      headers: { 'Authorization': `Klaviyo-API-Key ${key}`, 'revision': '2023-02-22' }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.detail || 'Klaviyo API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── MAILCHIMP ────────────────────────────────────────────────────
app.get('/api/mailchimp/lists', async (req, res) => {
  const key = process.env.MAILCHIMP_API_KEY;
  const prefix = process.env.MAILCHIMP_SERVER_PREFIX;
  if (!key || !prefix) return res.status(503).json({ error: 'MAILCHIMP_API_KEY oder MAILCHIMP_SERVER_PREFIX nicht konfiguriert' });
  try {
    const datacenter = key.split('-')[1] || prefix;
    const r = await fetch(`https://${datacenter}.api.mailchimp.com/3.0/lists`, {
      headers: { 'Authorization': `Basic ${Buffer.from(`anystring:${key}`).toString('base64')}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.detail || 'Mailchimp API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── PINTEREST ────────────────────────────────────────────────────
async function pinterestFetch(endpoint, opts = {}) {
  const url = `https://api.pinterest.com/v5/${endpoint}`;
  const res = await fetch(url, {
    ...opts,
    headers: { 'Authorization': `Bearer ${process.env.PINTEREST_ACCESS_TOKEN}`, 'Content-Type': 'application/json', ...(opts.headers||{}) }
  });
  if (!res.ok) throw new Error(`Pinterest ${res.status}: ${await res.text()}`);
  return res.json();
}

app.get('/api/pinterest/boards', async (req, res) => {
  const token = process.env.PINTEREST_ACCESS_TOKEN;
  if (!token) return res.status(503).json({ error: 'PINTEREST_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const data = await pinterestFetch('boards');
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/pinterest/pins', async (req, res) => {
  const token = process.env.PINTEREST_ACCESS_TOKEN;
  if (!token) return res.status(503).json({ error: 'PINTEREST_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { board_id, title, description, image_url, link } = req.body;
    if (!board_id || !title) return res.status(400).json({ error: 'board_id und title required' });
    const data = await pinterestFetch('pins', {
      method: 'POST',
      body: JSON.stringify({ board_id, title, description, media_source: { source_type: 'image_url', url: image_url }, link })
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── REDDIT ────────────────────────────────────────────────────
async function redditFetch(endpoint, opts = {}) {
  const auth = Buffer.from(`${process.env.REDDIT_CLIENT_ID}:${process.env.REDDIT_CLIENT_SECRET}`).toString('base64');
  const tokenRes = await fetch('https://www.reddit.com/api/v1/access_token', {
    method: 'POST',
    headers: { 'Authorization': `Basic ${auth}`, 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'RudiBot/1.0' },
    body: 'grant_type=client_credentials'
  });
  const tokenData = await tokenRes.json();
  const url = `https://oauth.reddit.com/${endpoint}`;
  const res = await fetch(url, {
    ...opts,
    headers: { 'Authorization': `Bearer ${tokenData.access_token}`, 'User-Agent': 'RudiBot/1.0', ...(opts.headers||{}) }
  });
  if (!res.ok) throw new Error(`Reddit ${res.status}: ${await res.text()}`);
  return res.json();
}

app.get('/api/reddit/hot/:subreddit', async (req, res) => {
  const clientId = process.env.REDDIT_CLIENT_ID;
  const clientSecret = process.env.REDDIT_CLIENT_SECRET;
  if (!clientId || !clientSecret) return res.status(503).json({ error: 'REDDIT_CLIENT_ID/SECRET nicht konfiguriert' });
  try {
    const limit = Math.min(parseInt(req.query.limit)||25, 100);
    const data = await redditFetch(`r/${req.params.subreddit}/hot?limit=${limit}`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── TWITTER / X ────────────────────────────────────────────────────
app.get('/api/twitter/me', async (req, res) => {
  const token = process.env.TWITTER_BEARER_TOKEN;
  if (!token) return res.status(503).json({ error: 'TWITTER_BEARER_TOKEN nicht konfiguriert' });
  try {
    const r = await fetch('https://api.x.com/2/users/me', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.detail || 'Twitter API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/twitter/tweet', async (req, res) => {
  const token = process.env.TWITTER_BEARER_TOKEN;
  if (!token) return res.status(503).json({ error: 'TWITTER_BEARER_TOKEN nicht konfiguriert' });
  try {
    const { text, reply_to } = req.body;
    if (!text) return res.status(400).json({ error: 'text required' });
    const body = { text };
    if (reply_to) body.reply = { in_reply_to_tweet_id: reply_to };
    const r = await fetch('https://api.x.com/2/tweets', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.detail || 'Twitter API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── LINKEDIN ────────────────────────────────────────────────────
app.get('/api/linkedin/me', async (req, res) => {
  const token = process.env.LINKEDIN_ACCESS_TOKEN;
  if (!token) return res.status(503).json({ error: 'LINKEDIN_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const r = await fetch('https://api.linkedin.com/v2/me', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'LinkedIn API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/linkedin/post', async (req, res) => {
  const token = process.env.LINKEDIN_ACCESS_TOKEN;
  if (!token) return res.status(503).json({ error: 'LINKEDIN_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { urn, text, url } = req.body;
    if (!urn || !text) return res.status(400).json({ error: 'urn und text required' });
    const body = {
      author: urn,
      lifecycleState: 'PUBLISHED',
      specificContent: {
        'com.linkedin.ugc.ShareContent': {
          shareCommentary: { text },
          shareMediaCategory: url ? 'ARTICLE' : 'NONE',
          media: url ? [{ status: 'READY', originalUrl: url }] : undefined
        }
      },
      visibility: { 'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC' }
    };
    const r = await fetch('https://api.linkedin.com/v2/ugcPosts', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0'
      },
      body: JSON.stringify(body)
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'LinkedIn API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── UPWORK ────────────────────────────────────────────────────
app.get('/api/upwork/profile', async (req, res) => {
  const consumerKey = process.env.UPWORK_CONSUMER_KEY;
  const consumerSecret = process.env.UPWORK_CONSUMER_SECRET;
  const accessToken = process.env.UPWORK_ACCESS_TOKEN;
  const accessSecret = process.env.UPWORK_ACCESS_SECRET;
  if (!consumerKey || !consumerSecret || !accessToken || !accessSecret) {
    return res.status(503).json({ error: 'Upwork OAuth credentials nicht konfiguriert' });
  }
  try {
    const OAuth = require('oauth').OAuth;
    const oa = new OAuth(
      'https://www.upwork.com/api/auth/v1/oauth/token/request',
      'https://www.upwork.com/api/auth/v1/oauth/token/access',
      consumerKey, consumerSecret, '1.0', null, 'HMAC-SHA1'
    );
    const data = await new Promise((resolve, reject) => {
      oa.get('https://www.upwork.com/api/profiles/v1/me.json', accessToken, accessSecret,
        (err, data) => err ? reject(err) : resolve(JSON.parse(data))
      );
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/upwork/jobs', async (req, res) => {
  const consumerKey = process.env.UPWORK_CONSUMER_KEY;
  const consumerSecret = process.env.UPWORK_CONSUMER_SECRET;
  const accessToken = process.env.UPWORK_ACCESS_TOKEN;
  const accessSecret = process.env.UPWORK_ACCESS_SECRET;
  if (!consumerKey || !consumerSecret || !accessToken || !accessSecret) {
    return res.status(503).json({ error: 'Upwork OAuth credentials nicht konfiguriert' });
  }
  try {
    const { query = 'javascript', paging = '0;10' } = req.query;
    const OAuth = require('oauth').OAuth;
    const oa = new OAuth(
      'https://www.upwork.com/api/auth/v1/oauth/token/request',
      'https://www.upwork.com/api/auth/v1/oauth/token/access',
      consumerKey, consumerSecret, '1.0', null, 'HMAC-SHA1'
    );
    const data = await new Promise((resolve, reject) => {
      oa.get(`https://www.upwork.com/api/hr/v3/freelancers/search/jobs.json?q=${encodeURIComponent(query)}&paging=${paging}`,
        accessToken, accessSecret,
        (err, data) => err ? reject(err) : resolve(JSON.parse(data))
      );
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── GUMROAD ────────────────────────────────────────────────────
app.get('/api/gumroad/user', async (req, res) => {
  const token = process.env.GUMROAD_ACCESS_TOKEN;
  if (!token) return res.status(503).json({ error: 'GUMROAD_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const r = await fetch(`https://api.gumroad.com/v2/user?access_token=${token}`);
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'Gumroad API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/gumroad/products', async (req, res) => {
  const token = process.env.GUMROAD_ACCESS_TOKEN;
  if (!token) return res.status(503).json({ error: 'GUMROAD_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const r = await fetch(`https://api.gumroad.com/v2/products?access_token=${token}`);
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'Gumroad API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/gumroad/products', async (req, res) => {
  const token = process.env.GUMROAD_ACCESS_TOKEN;
  if (!token) return res.status(503).json({ error: 'GUMROAD_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { name, description, price, file_url } = req.body;
    if (!name || !description || !price) {
      return res.status(400).json({ error: 'name, description und price required' });
    }
    const body = new URLSearchParams({
      access_token: token, name, description,
      price: price.toString(), // in cents
      is_recurring: 'false'
    });
    if (file_url) body.append('file_url', file_url);
    const r = await fetch('https://api.gumroad.com/v2/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'Gumroad API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── ETSY ────────────────────────────────────────────────────
app.get('/api/etsy/shop/:shopId', async (req, res) => {
  const apiKey = process.env.ETSY_API_KEY;
  const accessToken = process.env.ETSY_ACCESS_TOKEN;
  if (!apiKey) return res.status(503).json({ error: 'ETSY_API_KEY nicht konfiguriert' });
  try {
    const { shopId } = req.params;
    const r = await fetch(`https://openapi.etsy.com/v3/application/shops/${shopId}`, {
      headers: { 'x-api-key': apiKey, ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {}) }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error || 'Etsy API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/etsy/shop/:shopId/listings', async (req, res) => {
  const apiKey = process.env.ETSY_API_KEY;
  const accessToken = process.env.ETSY_ACCESS_TOKEN;
  if (!apiKey || !accessToken) return res.status(503).json({ error: 'ETSY_API_KEY/ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { shopId } = req.params;
    const limit = Math.min(parseInt(req.query.limit)||25, 100);
    const r = await fetch(`https://openapi.etsy.com/v3/application/shops/${shopId}/listings?limit=${limit}`, {
      headers: { 'x-api-key': apiKey, 'Authorization': `Bearer ${accessToken}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error || 'Etsy API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── PRODUCT HUNT ────────────────────────────────────────────────────
app.post('/api/producthunt/graphql', async (req, res) => {
  const token = process.env.PRODUCT_HUNT_TOKEN;
  if (!token) return res.status(503).json({ error: 'PRODUCT_HUNT_TOKEN nicht konfiguriert' });
  try {
    const { query, variables } = req.body;
    if (!query) return res.status(400).json({ error: 'GraphQL query required' });
    const r = await fetch('https://api.producthunt.com/v2/api/graphql', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ query, variables })
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.errors?.[0]?.message || 'Product Hunt API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/producthunt/posts', async (req, res) => {
  const token = process.env.PRODUCT_HUNT_TOKEN;
  if (!token) return res.status(503).json({ error: 'PRODUCT_HUNT_TOKEN nicht konfiguriert' });
  try {
    const query = `
      query {
        posts(first: 20, order: RANKING) {
          edges {
            node {
              id
              name
              tagline
              url
              votesCount
              commentsCount
              createdAt
              featuredAt
              maker {
                id
                name
                username
                url
              }
            }
          }
        }
      }
    `;
    const r = await fetch('https://api.producthunt.com/v2/api/graphql', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ query })
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.errors?.[0]?.message || 'Product Hunt API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── UDEMY ────────────────────────────────────────────────────
app.get('/api/udemy/courses', async (req, res) => {
  const token = process.env.UDEMY_API_KEY;
  if (!token) return res.status(503).json({ error: 'UDEMY_API_KEY nicht konfiguriert' });
  try {
    const { page = 1, page_size = 20, search } = req.query;
    let url = `https://www.udemy.com/api-2.0/courses/?page=${page}&page_size=${page_size}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const r = await fetch(url, {
      headers: { 'Authorization': `Basic ${Buffer.from(token + ':').toString('base64')}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.detail || 'Udemy API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── ZAPIER ────────────────────────────────────────────────────
app.post('/api/zapier/webhook', async (req, res) => {
  const webhookUrl = process.env.ZAPIER_WEBHOOK_URL;
  if (!webhookUrl) return res.status(503).json({ error: 'ZAPIER_WEBHOOK_URL nicht konfiguriert' });
  try {
    const r = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const data = await r.json();
    if (r.ok) res.json({ success: true, data });
    else res.status(r.status).json({ error: 'Zapier Webhook Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── NOTION ────────────────────────────────────────────────────
app.get('/api/notion/databases', async (req, res) => {
  const token = process.env.NOTION_API_KEY;
  if (!token) return res.status(503).json({ error: 'NOTION_API_KEY nicht konfiguriert' });
  try {
    const r = await fetch('https://api.notion.com/v1/databases', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Notion-Version': '2022-06-28'
      }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'Notion API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/notion/pages', async (req, res) => {
  const token = process.env.NOTION_API_KEY;
  if (!token) return res.status(503).json({ error: 'NOTION_API_KEY nicht konfiguriert' });
  try {
    const { database_id, properties } = req.body;
    if (!database_id || !properties) return res.status(400).json({ error: 'database_id und properties required' });
    const r = await fetch('https://api.notion.com/v1/pages', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ parent: { database_id }, properties })
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'Notion API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── AIRTABLE ────────────────────────────────────────────────────
app.get('/api/airtable/records/:baseId/:tableId', async (req, res) => {
  const token = process.env.AIRTABLE_API_KEY;
  if (!token) return res.status(503).json({ error: 'AIRTABLE_API_KEY nicht konfiguriert' });
  try {
    const { baseId, tableId } = req.params;
    const limit = Math.min(parseInt(req.query.limit)||100, 1000);
    const r = await fetch(`https://api.airtable.com/v0/${baseId}/${tableId}?maxRecords=${limit}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error?.message || 'Airtable API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/airtable/records/:baseId/:tableId', async (req, res) => {
  const token = process.env.AIRTABLE_API_KEY;
  if (!token) return res.status(503).json({ error: 'AIRTABLE_API_KEY nicht konfiguriert' });
  try {
    const { baseId, tableId } = req.params;
    const { records } = req.body;
    if (!records || !Array.isArray(records)) return res.status(400).json({ error: 'records array required' });
    const r = await fetch(`https://api.airtable.com/v0/${baseId}/${tableId}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ records })
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error?.message || 'Airtable API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── MAILCHIMP ────────────────────────────────────────────────────
app.get('/api/mailchimp/lists', async (req, res) => {
  const key = process.env.MAILCHIMP_API_KEY;
  const prefix = process.env.MAILCHIMP_SERVER_PREFIX;
  if (!key || !prefix) return res.status(503).json({ error: 'MAILCHIMP_API_KEY oder MAILCHIMP_SERVER_PREFIX nicht konfiguriert' });
  try {
    const datacenter = key.split('-')[1] || prefix;
    const r = await fetch(`https://${datacenter}.api.mailchimp.com/3.0/lists`, {
      headers: { 'Authorization': `Bearer ${key}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.detail || 'Mailchimp API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── INTERNAL STORAGE SYSTEMS ────────────────────────────────────────
const os = require('os');

// Get system directories
function getSystemDirectories() {
  const homeDir = os.homedir();
  const platform = os.platform();
  
  const dirs = {
    desktop: path.join(homeDir, 'Desktop'),
    downloads: path.join(homeDir, 'Downloads'),
    documents: path.join(homeDir, 'Documents'),
    pictures: path.join(homeDir, 'Pictures'),
    music: path.join(homeDir, 'Music'),
    videos: path.join(homeDir, 'Videos'),
    applications: platform === 'darwin' ? '/Applications' : platform === 'win32' ? 'C:\\Program Files' : '/usr/bin',
    temp: os.tmpdir(),
    home: homeDir,
    user: platform === 'darwin' ? '/Users' : platform === 'win32' ? 'C:\\Users' : '/home'
  };
  
  // Add Mac-specific directories
  if (platform === 'darwin') {
    dirs.macosApplications = '/Applications';
    dirs.library = path.join(homeDir, 'Library');
    dirs.caches = path.join(homeDir, 'Library', 'Caches');
    dirs.logs = path.join(homeDir, 'Library', 'Logs');
    dirs.preferences = path.join(homeDir, 'Library', 'Preferences');
  }
  
  return dirs;
}

// Deep scan directory
function deepScanDirectory(dirPath, maxDepth = 3, currentDepth = 0) {
  try {
    if (currentDepth >= maxDepth) return { files: [], folders: [], size: 0, count: 0 };
    
    const items = fs.readdirSync(dirPath, { withFileTypes: true });
    const result = { files: [], folders: [], size: 0, count: 0 };
    
    for (const item of items) {
      const fullPath = path.join(dirPath, item.name);
      try {
        const stats = fs.statSync(fullPath);
        const itemInfo = {
          name: item.name,
          path: fullPath,
          size: stats.size,
          modified: stats.mtime,
          type: item.isDirectory() ? 'folder' : 'file',
          extension: item.isFile() ? path.extname(item.name) : null
        };
        
        if (item.isDirectory()) {
          result.folders.push(itemInfo);
          if (currentDepth < maxDepth - 1) {
            const subScan = deepScanDirectory(fullPath, maxDepth, currentDepth + 1);
            result.size += subScan.size;
            result.count += subScan.count;
          }
        } else {
          result.files.push(itemInfo);
          result.size += stats.size;
          result.count++;
        }
      } catch (err) {
        // Skip files/folders we can't access
        continue;
      }
    }
    
    return result;
  } catch (error) {
    return { files: [], folders: [], size: 0, count: 0, error: error.message };
  }
}

app.get('/api/storage/directories', (_, res) => {
  try {
    const dirs = getSystemDirectories();
    const platform = os.platform();
    res.json({
      platform,
      directories: dirs,
      hostname: os.hostname(),
      userInfo: os.userInfo()
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/storage/scan/:path(*)', async (req, res) => {
  try {
    const scanPath = req.params.path || os.homedir();
    const maxDepth = Math.min(parseInt(req.query.depth) || 2, 5);
    const result = deepScanDirectory(scanPath, maxDepth);
    
    // Format sizes
    const formatSize = (bytes) => {
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let size = bytes;
      let unitIndex = 0;
      while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
      }
      return `${size.toFixed(2)} ${units[unitIndex]}`;
    };
    
    res.json({
      path: scanPath,
      depth: maxDepth,
      summary: {
        totalFiles: result.files.length,
        totalFolders: result.folders.length,
        totalSize: formatSize(result.size),
        totalItems: result.count
      },
      files: result.files.slice(0, 100), // Limit to first 100 files
      folders: result.folders.slice(0, 50), // Limit to first 50 folders
      hasMore: result.files.length > 100 || result.folders.length > 50
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/storage/desktop', async (req, res) => {
  try {
    const desktopPath = path.join(os.homedir(), 'Desktop');
    const result = deepScanDirectory(desktopPath, 2);
    res.json({
      path: desktopPath,
      files: result.files,
      folders: result.folders,
      summary: {
        files: result.files.length,
        folders: result.folders.length,
        size: result.size
      }
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/storage/downloads', async (req, res) => {
  try {
    const downloadsPath = path.join(os.homedir(), 'Downloads');
    const result = deepScanDirectory(downloadsPath, 2);
    
    // Sort by modification date (newest first)
    const sortedFiles = result.files.sort((a, b) => new Date(b.modified) - new Date(a.modified));
    
    res.json({
      path: downloadsPath,
      files: sortedFiles.slice(0, 50), // Show 50 most recent files
      folders: result.folders,
      summary: {
        files: result.files.length,
        folders: result.folders.length,
        size: result.size
      }
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── CLOUD STORAGE APIS ────────────────────────────────────────────────

// Google Drive API
app.get('/api/googledrive/files', async (req, res) => {
  const accessToken = process.env.GOOGLE_DRIVE_ACCESS_TOKEN;
  if (!accessToken) return res.status(503).json({ error: 'GOOGLE_DRIVE_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { pageSize = 10, query = '' } = req.query;
    const url = `https://www.googleapis.com/drive/v3/files?pageSize=${pageSize}&q=${encodeURIComponent(query)}&fields=files(id,name,mimeType,size,modifiedTime,parents)`;
    const r = await fetch(url, {
      headers: { 'Authorization': `Bearer ${accessToken}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error?.message || 'Google Drive API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/googledrive/upload', async (req, res) => {
  const accessToken = process.env.GOOGLE_DRIVE_ACCESS_TOKEN;
  if (!accessToken) return res.status(503).json({ error: 'GOOGLE_DRIVE_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { name, parents = [] } = req.body;
    if (!name) return res.status(400).json({ error: 'name required' });
    
    // Create metadata
    const metadata = { name, parents };
    const r = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(metadata)
    });
    
    if (r.ok) {
      const uploadUrl = r.headers.get('location');
      res.json({ uploadUrl, message: 'Use this URL to upload file content' });
    } else {
      const data = await r.json();
      res.status(r.status).json({ error: data.error?.message || 'Google Drive Upload Error' });
    }
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Dropbox API
app.get('/api/dropbox/files', async (req, res) => {
  const accessToken = process.env.DROPBOX_ACCESS_TOKEN;
  if (!accessToken) return res.status(503).json({ error: 'DROPBOX_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { path = '', limit = 10 } = req.query;
    const url = `https://api.dropboxapi.com/2/files/list_folder?path=${encodeURIComponent(path)}&limit=${limit}`;
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error_summary || 'Dropbox API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// OneDrive API
app.get('/api/onedrive/files', async (req, res) => {
  const accessToken = process.env.ONEDRIVE_ACCESS_TOKEN;
  if (!accessToken) return res.status(503).json({ error: 'ONEDRIVE_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const { top = 10, filter = '' } = req.query;
    let url = `https://graph.microsoft.com/v1.0/me/drive/root/children?$top=${top}`;
    if (filter) url += `&$filter=${encodeURIComponent(filter)}`;
    
    const r = await fetch(url, {
      headers: { 'Authorization': `Bearer ${accessToken}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error?.message || 'OneDrive API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// iCloud API (limited)
app.get('/api/icloud/info', async (req, res) => {
  const appleId = process.env.ICLOUD_APPLE_ID;
  const password = process.env.ICLOUD_PASSWORD;
  if (!appleId || !password) return res.status(503).json({ error: 'iCloud credentials nicht konfiguriert' });
  try {
    // Note: iCloud API requires third-party libraries, this is a placeholder
    res.json({ 
      message: 'iCloud API requires additional setup',
      recommendation: 'Use icloud.js npm package or pyicloud for Python',
      status: 'placeholder'
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── NOTES SYSTEMS ────────────────────────────────────────────────────

// Evernote API
app.get('/api/evernote/notebooks', async (req, res) => {
  const token = process.env.EVERNOTE_TOKEN;
  if (!token) return res.status(503).json({ error: 'EVERNOTE_TOKEN nicht konfiguriert' });
  try {
    // Note: Evernote API requires developer token
    res.json({
      message: 'Evernote API integration requires developer token setup',
      status: 'placeholder',
      endpoint: 'https://sandbox.evernote.com/edam/notebook'
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// OneNote API
app.get('/api/onenote/notebooks', async (req, res) => {
  const accessToken = process.env.ONENOTE_ACCESS_TOKEN;
  if (!accessToken) return res.status(503).json({ error: 'ONENOTE_ACCESS_TOKEN nicht konfiguriert' });
  try {
    const url = 'https://graph.microsoft.com/v1.0/me/onenote/notebooks';
    const r = await fetch(url, {
      headers: { 'Authorization': `Bearer ${accessToken}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error?.message || 'OneNote API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Apple Notes (limited)
app.get('/api/apple/notes', async (req, res) => {
  res.json({
    message: 'Apple Notes API is not publicly available',
    alternatives: ['Use Shortcuts app', 'Export to other formats', 'Use third-party tools'],
    status: 'not_available'
  });
});

// ── IDE INTEGRATION ────────────────────────────────────────────────────

// Visual Studio Code
app.get('/api/vscode/extensions', async (req, res) => {
  try {
    const { search = '', pageSize = 10 } = req.query;
    const url = `https://marketplace.visualstudio.com/_apis/publishers/v1/extensionquery?pageSize=${pageSize}&searchTerm=${encodeURIComponent(search)}`;
    const r = await fetch(url);
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: 'VS Code API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// GitHub Codespaces
app.get('/api/codespaces/list', async (req, res) => {
  const token = process.env.GITHUB_TOKEN;
  if (!token) return res.status(503).json({ error: 'GITHUB_TOKEN nicht konfiguriert' });
  try {
    const r = await fetch('https://api.github.com/user/codespaces', {
      headers: { 'Authorization': `token ${token}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.message || 'GitHub Codespaces Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── WINDSURF MONITORING ───────────────────────────────────────────────────
app.get('/api/windsurf/status', async (req, res) => {
  try {
    // Check if windsurf-monitoring.js is running
    const r = await fetch('http://localhost:9001/monitoring-stats', { 
      signal: AbortSignal.timeout(2000) 
    });
    
    if (r.ok) {
      const data = await r.json();
      res.json({
        status: 'running',
        uptime: data.uptime,
        checks: data.checks?.length || 0,
        alerts: data.alerts?.length || 0,
        lastCheck: data.timestamp
      });
    } else {
      res.json({
        status: 'stopped',
        message: 'Windsurf monitoring is not running',
        action: 'Start with: node windsurf-monitoring.js'
      });
    }
  } catch(e) {
    res.json({
      status: 'stopped',
      message: 'Windsurf monitoring is not running',
      action: 'Start with: node windsurf-monitoring.js'
    });
  }
});

// ── CLAUDE DESKTOP INTEGRATION ───────────────────────────────────────────
app.post('/api/claude/desktop/command', async (req, res) => {
  try {
    const { command, args = [] } = req.body;
    if (!command) return res.status(400).json({ error: 'command required' });
    
    // Execute system command (be careful with security)
    const { exec } = require('child_process');
    exec(`${command} ${args.join(' ')}`, (error, stdout, stderr) => {
      if (error) {
        res.status(500).json({ error: error.message, stderr });
      } else {
        res.json({ stdout, stderr, success: true });
      }
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

app.get('/api/claude/desktop/system', async (req, res) => {
  try {
    const { execSync } = require('child_process');
    
    const systemInfo = {
      platform: os.platform(),
      arch: os.arch(),
      hostname: os.hostname(),
      uptime: os.uptime(),
      loadavg: os.loadavg(),
      totalmem: os.totalmem(),
      freemem: os.freemem(),
      cpus: os.cpus(),
      networkInterfaces: os.networkInterfaces(),
      userInfo: os.userInfo()
    };
    
    // Add Mac-specific info
    if (os.platform() === 'darwin') {
      try {
        const macVersion = execSync('sw_vers -productVersion').toString().trim();
        const macBuild = execSync('sw_vers -buildVersion').toString().trim();
        systemInfo.mac = { version: macVersion, build: macBuild };
      } catch (e) {
        systemInfo.mac = { error: 'Could not get macOS version' };
      }
    }
    
    res.json(systemInfo);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── ADAPTIVE DEEP-SCAN SYSTEM ───────────────────────────────────────────
const AdaptiveDeepScanMaster = require('../adaptive-deepscan-master');
const AdaptiveDeepScanSystem = require('../adaptive-deepscan-system');

// Initialize adaptive deep scan system
const deepScanSystem = new AdaptiveDeepScanSystem({
  reportsPath: path.join(__dirname, '../reports'),
  autoCleanup: true
});

// Execute adaptive deep scan
app.post('/api/deepscan/execute', async (req, res) => {
  try {
    const { targetPath, options = {} } = req.body;
    if (!targetPath) return res.status(400).json({ error: 'targetPath required' });
    
    // Validate path exists
    if (!fs.existsSync(targetPath)) {
      return res.status(404).json({ error: 'Path does not exist' });
    }
    
    // Execute scan
    const report = await deepScanSystem.executeScan(targetPath, options);
    
    res.json({
      success: true,
      scan_id: report.scan_id,
      statistics: report.statistics,
      security_score: report.security_score,
      security_issues_count: report.security_issues.length,
      report_path: report.report_path,
      duration: report.duration_human
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Quick scan endpoint
app.get('/api/deepscan/quick/:path(*)', async (req, res) => {
  try {
    const scanPath = req.params.path || os.homedir();
    const maxDepth = Math.min(parseInt(req.query.depth) || 2, 3);
    
    const scanner = new AdaptiveDeepScanMaster({
      maxDepth,
      securityScan: true,
      generateReports: false
    });
    
    const result = await scanner.scanDirectory(scanPath);
    const report = scanner.generateReport();
    
    res.json({
      path: scanPath,
      depth: maxDepth,
      summary: {
        totalFiles: result.files.length,
        totalFolders: result.folders.length,
        totalSize: scanner.formatSize(result.size),
        securityIssues: report.security_issues.length
      },
      files: result.files.slice(0, 20),
      folders: result.folders.slice(0, 10)
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Get scan history
app.get('/api/deepscan/history', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    const history = deepScanSystem.getScanHistory(limit);
    
    res.json({
      total: history.length,
      scans: history.map(scan => ({
        file: scan.file,
        timestamp: scan.mtime.toISOString(),
        size: scan.size
      }))
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Get system status
app.get('/api/deepscan/status', async (req, res) => {
  try {
    const status = deepScanSystem.getSystemStatus();
    res.json(status);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Environment security hardening
app.post('/api/deepscan/security/harden', async (req, res) => {
  try {
    const { targetPath = '.' } = req.body;
    
    // Find .env files
    const envFiles = [];
    const findEnvFiles = (dir, depth = 0) => {
      if (depth > 3) return;
      
      try {
        const items = fs.readdirSync(dir, { withFileTypes: true });
        for (const item of items) {
          const fullPath = path.join(dir, item.name);
          if (item.isDirectory() && !item.name.startsWith('.')) {
            findEnvFiles(fullPath, depth + 1);
          } else if (item.isFile() && item.name === '.env') {
            envFiles.push(fullPath);
          }
        }
      } catch (e) {
        // Skip inaccessible directories
      }
    };
    
    findEnvFiles(targetPath);
    
    const hardeningActions = [];
    
    for (const envFile of envFiles) {
      try {
        const stats = fs.statSync(envFile);
        const perms = stats.mode.toString(8);
        
        // Check if permissions are too open
        if ((stats.mode & 0o077) !== 0) {
          // Restrict permissions to owner only
          fs.chmodSync(envFile, 0o600);
          hardeningActions.push({
            file: envFile,
            action: 'permissions_restricted',
            old_permissions: perms,
            new_permissions: '600'
          });
        }
        
        // Check if file is in a secure location
        const isInSecureLocation = envFile.includes('private') || 
                                 envFile.includes('secure') ||
                                 envFile.includes('.config');
        
        if (!isInSecureLocation) {
          hardeningActions.push({
            file: envFile,
            action: 'location_warning',
            recommendation: 'Move .env file to secure location or encrypt it'
          });
        }
        
      } catch (e) {
        hardeningActions.push({
          file: envFile,
          action: 'error',
          error: e.message
        });
      }
    }
    
    res.json({
      target_path: targetPath,
      env_files_found: envFiles.length,
      hardening_actions: hardeningActions,
      security_score: hardeningActions.length === 0 ? 100 : Math.max(0, 100 - (hardeningActions.length * 10))
    });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── DIGISTORE24 ────────────────────────────────────────────────────
async function digistoreFetch(endpoint, opts = {}) {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) throw new Error('DIGISTORE_API_KEY nicht konfiguriert');
  
  const url = `https://www.digistore24.com/api/v1/${endpoint}`;
  const res = await fetch(url, {
    ...opts,
    headers: { 
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...(opts.headers||{}) 
    }
  });
  
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Digistore24 ${res.status}: ${errorText}`);
  }
  
  return res.json();
}

// Get all products
app.get('/api/digistore/products', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const limit = Math.min(parseInt(req.query.limit)||50, 250);
    const page = parseInt(req.query.page)||1;
    const status = req.query.status || 'active';
    
    const data = await digistoreFetch(`products?limit=${limit}&page=${page}&status=${status}`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Get specific product
app.get('/api/digistore/products/:id', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const data = await digistoreFetch(`products/${req.params.id}`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Create product
app.post('/api/digistore/products', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const data = await digistoreFetch('products', {
      method: 'POST',
      body: JSON.stringify(req.body)
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Update product
app.put('/api/digistore/products/:id', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const data = await digistoreFetch(`products/${req.params.id}`, {
      method: 'PUT',
      body: JSON.stringify(req.body)
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Get orders
app.get('/api/digistore/orders', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const limit = Math.min(parseInt(req.query.limit)||50, 250);
    const page = parseInt(req.query.page)||1;
    const status = req.query.status || '';
    const fromDate = req.query.from_date || '';
    const toDate = req.query.to_date || '';
    
    let endpoint = `orders?limit=${limit}&page=${page}`;
    if (status) endpoint += `&status=${status}`;
    if (fromDate) endpoint += `&from_date=${fromDate}`;
    if (toDate) endpoint += `&to_date=${toDate}`;
    
    const data = await digistoreFetch(endpoint);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ============================================================
// NOTION API ENDPOINTS
// ============================================================

// Get Notion database info
app.get('/api/notion/database', async (req, res) => {
  const apiKey = process.env.NOTION_API_KEY;
  const databaseId = process.env.NOTION_DATABASE_ID;
  
  if (!apiKey) {
    return res.status(503).json({ error: 'NOTION_API_KEY nicht konfiguriert' });
  }
  
  try {
    const response = await fetch(`https://api.notion.com/v1/databases/${databaseId}`, {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Notion-Version': '2022-06-28'
      }
    });
    
    if (!response.ok) {
      throw new Error(`Notion API Error: ${response.status}`);
    }
    
    const data = await response.json();
    res.json({ success: true, data });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// Create Notion page
app.post('/api/notion/page', async (req, res) => {
  const apiKey = process.env.NOTION_API_KEY;
  const databaseId = process.env.NOTION_DATABASE_ID;
  const { title, content } = req.body;
  
  if (!apiKey) {
    return res.status(503).json({ error: 'NOTION_API_KEY nicht konfiguriert' });
  }
  
  if (!title) {
    return res.status(400).json({ error: 'Title ist erforderlich' });
  }
  
  try {
    const pageData = {
      parent: { database_id: databaseId },
      properties: {
        Name: { title: [{ text: { content: title } }] },
        Created: { date: { start: new Date().toISOString() } }
      }
    };
    
    if (content) {
      pageData.properties.Content = { rich_text: [{ text: { content: content } }] };
    }
    
    const response = await fetch('https://api.notion.com/v1/pages', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
      },
      body: JSON.stringify(pageData)
    });
    
    if (!response.ok) {
      throw new Error(`Notion API Error: ${response.status}`);
    }
    
    const data = await response.json();
    res.json({ success: true, data });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// Get specific order
app.get('/api/digistore/orders/:id', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const data = await digistoreFetch(`orders/${req.params.id}`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Get order details (including buyer info)
app.get('/api/digistore/orders/:id/details', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const data = await digistoreFetch(`orders/${req.params.id}/details`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Cancel order
app.post('/api/digistore/orders/:id/cancel', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const data = await digistoreFetch(`orders/${req.params.id}/cancel`, {
      method: 'POST',
      body: JSON.stringify(req.body)
    });
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Get affiliates
app.get('/api/digistore/affiliates', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const limit = Math.min(parseInt(req.query.limit)||50, 250);
    const page = parseInt(req.query.page)||1;
    
    const data = await digistoreFetch(`affiliates?limit=${limit}&page=${page}`);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Get sales statistics
app.get('/api/digistore/stats', async (req, res) => {
  const apiKey = process.env.DIGISTORE_API_KEY;
  if (!apiKey) return res.status(503).json({ error: 'DIGISTORE_API_KEY nicht konfiguriert' });
  try {
    const fromDate = req.query.from_date || '';
    const toDate = req.query.to_date || '';
    
    let endpoint = 'stats';
    if (fromDate) endpoint += `?from_date=${fromDate}`;
    if (toDate) endpoint += `${fromDate ? '&' : '?'}to_date=${toDate}`;
    
    const data = await digistoreFetch(endpoint);
    res.json(data);
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// Digistore24 webhook handler
app.post('/webhooks/digistore24/:event', express.raw({ type: 'application/json' }), (req, res) => {
  try {
    const event = req.params.event;
    const payload = JSON.parse(req.body.toString());
    
    console.log(`🔔 Digistore24 Webhook: ${event}`, JSON.stringify(payload).slice(0,200));
    
    // Process different webhook events
    setImmediate(async () => {
      try {
        switch (event) {
          case 'order_created':
            console.log(`💰 Neue Digistore24 Bestellung: ${payload.order_id || 'N/A'}`);
            // Optional: Send notification via Telegram
            if (process.env.TELEGRAM_BOT_TOKEN && !process.env.TELEGRAM_BOT_TOKEN.includes('PLACEHOLDER')) {
              // Could implement Telegram notification here
            }
            break;
          case 'order_paid':
            console.log(`✅ Digistore24 Bestellung bezahlt: ${payload.order_id || 'N/A'}`);
            break;
          case 'order_cancelled':
            console.log(`❌ Digistore24 Bestellung storniert: ${payload.order_id || 'N/A'}`);
            break;
          case 'refund_requested':
            console.log(`🔄 Digistore24 Rückerstattung angefragt: ${payload.order_id || 'N/A'}`);
            break;
          default:
            console.log(`📋 Digistore24 Webhook verarbeitet: ${event}`);
        }
      } catch(err) {
        console.error('Digistore24 Webhook processing error:', err);
      }
    });
    
    res.status(200).json({ received: true });
  } catch (error) {
    console.error('❌ Digistore24 Webhook processing error:', error.message);
    res.status(400).json({ error: 'Invalid webhook data' });
  }
});

// ── STRIPE ────────────────────────────────────────────────────
app.get('/api/stripe/balance', async (req, res) => {
  const key = process.env.STRIPE_API_KEY;
  if (!key) return res.status(503).json({ error: 'STRIPE_API_KEY nicht konfiguriert' });
  try {
    const r = await fetch('https://api.stripe.com/v1/balance', {
      headers: { 'Authorization': `Bearer ${key}` }
    });
    const data = await r.json();
    if (r.ok) res.json(data);
    else res.status(r.status).json({ error: data.error?.message || 'Stripe API Error' });
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── GOOGLE AI (Gemini) ──────────────────────────────────────────
app.post('/api/ai/gemini', async (req, res) => {
  const key = process.env.GOOGLE_AI_API_KEY;
  if (!key) return res.status(503).json({ error: 'GOOGLE_AI_API_KEY nicht konfiguriert' });
  try {
    const { prompt, max_tokens = 1024 } = req.body;
    if (!prompt) return res.status(400).json({ error: 'prompt required' });
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${key}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
    });
    const data = await r.json();
    if (r.ok) {
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '';
      res.json({ text, model: 'gemini-2.0-flash' });
    } else {
      res.status(r.status).json({ error: data.error?.message || 'Google AI API Error' });
    }
  } catch(e) { res.status(500).json({ error: e.message }); }
});

// ── STATUS ────────────────────────────────────────────────────
app.get('/api/status', (_, res) => {
  res.json({
    services: {
      anthropic:  { configured: !!process.env.ANTHROPIC_API_KEY && !process.env.ANTHROPIC_API_KEY.includes('PLACEHOLDER'),  name: 'Claude AI' },
      openai:     { configured: !!process.env.OPENAI_API_KEY && !process.env.OPENAI_API_KEY.includes('PLACEHOLDER'),     name: 'OpenAI' },
      perplexity: { configured: !!process.env.PERPLEXITY_API_KEY && !process.env.PERPLEXITY_API_KEY.includes('PLACEHOLDER'), name: 'Perplexity' },
      shopify1:   { configured: !!TOK && !TOK.includes('PLACEHOLDER'),  store: SHOP  || 'nicht gesetzt' },
      github:     { configured: !!GH_TOK && !GH_TOK.includes('PLACEHOLDER'), user: GH_USER },
      telegram:   { configured: !!process.env.TELEGRAM_BOT_TOKEN && !process.env.TELEGRAM_BOT_TOKEN.includes('PLACEHOLDER') },
      sendgrid:   { configured: !!process.env.SENDGRID_API_KEY && !process.env.SENDGRID_API_KEY.includes('PLACEHOLDER') },
      supabase:   { configured: !!process.env.SUPABASE_URL && !!process.env.SUPABASE_ANON_KEY && !process.env.SUPABASE_ANON_KEY.includes('PLACEHOLDER') },
      printify:   { configured: !!process.env.PRINTIFY_API_KEY && !!process.env.PRINTIFY_SHOP_ID && !process.env.PRINTIFY_API_KEY.includes('PLACEHOLDER') },
      stripe:     { configured: !!process.env.STRIPE_API_KEY && !process.env.STRIPE_API_KEY.includes('PLACEHOLDER') },
      digistore24: { configured: !!process.env.DIGISTORE_API_KEY && !process.env.DIGISTORE_API_KEY.includes('PLACEHOLDER'), name: 'Digistore24' },
    },
    timestamp: new Date().toISOString()
  });
});

// ── 404 + Error Handler ───────────────────────────────────────
app.use((req, res) => res.status(404).json({ error: `Route nicht gefunden: ${req.method} ${req.path}` }));
app.use((err, req, res, next) => {
  console.error('Server Error:', err);
  res.status(500).json({ error: err.message || 'Internal Server Error' });
});

// ============================================================
// WHATSAPP BUSINESS API ENDPOINTS
// ============================================================

// WhatsApp Webhook verification
app.get('/api/whatsapp/webhook', (req, res) => {
  const mode = req.query['hub.mode'];
  const token = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];
  
  const verifyToken = process.env.WHATSAPP_WEBHOOK_VERIFY_TOKEN;
  
  if (mode && token) {
    if (mode === 'subscribe' && token === verifyToken) {
      console.log('✅ WhatsApp Webhook verified');
      return res.status(200).send(challenge);
    }
  }
  
  res.status(403).send('Forbidden');
});

// Send WhatsApp message API endpoint
app.post('/api/whatsapp/send', async (req, res) => {
  const { to, message } = req.body;
  const phoneNumberId = process.env.WHATSAPP_PHONE_ID;
  const accessToken = process.env.WHATSAPP_ACCESS_TOKEN;
  
  if (!phoneNumberId || !accessToken || accessToken.includes('PLACEHOLDER')) {
    return res.status(503).json({ error: 'WhatsApp API nicht konfiguriert' });
  }
  
  if (!to || !message) {
    return res.status(400).json({ error: 'to and message are required' });
  }
  
  try {
    const response = await fetch(`https://graph.facebook.com/v18.0/${phoneNumberId}/messages`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        messaging_product: 'whatsapp',
        to: to,
        text: { body: message }
      })
    });
    
    if (response.ok) {
      const data = await response.json();
      res.json({ success: true, data });
    } else {
      const error = await response.text();
      res.status(500).json({ success: false, error: `WhatsApp API Error: ${error}` });
    }
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// DISCORD BOT API ENDPOINTS
// ============================================================

// Discord bot info
app.get('/api/discord/info', async (req, res) => {
  const botToken = process.env.DISCORD_BOT_TOKEN;
  
  if (!botToken || botToken.includes('PLACEHOLDER')) {
    return res.status(503).json({ error: 'DISCORD_BOT_TOKEN nicht konfiguriert' });
  }
  
  try {
    const response = await fetch('https://discord.com/api/v10/users/@me', {
      headers: {
        'Authorization': `Bot ${botToken}`
      }
    });
    
    if (response.ok) {
      const botInfo = await response.json();
      res.json({ success: true, data: botInfo });
    } else {
      throw new Error(`Discord API Error: ${response.status}`);
    }
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// TWITTER/X API v2 ENDPOINTS
// ============================================================

// Twitter user info
app.get('/api/twitter/me', async (req, res) => {
  const bearerToken = process.env.TWITTER_BEARER_TOKEN;
  
  if (!bearerToken || bearerToken.includes('PLACEHOLDER')) {
    return res.status(503).json({ error: 'TWITTER_BEARER_TOKEN nicht konfiguriert' });
  }
  
  try {
    const response = await fetch('https://api.twitter.com/2/users/me', {
      headers: {
        'Authorization': `Bearer ${bearerToken}`
      }
    });
    
    if (response.ok) {
      const userData = await response.json();
      res.json({ success: true, data: userData });
    } else {
      throw new Error(`Twitter API Error: ${response.status}`);
    }
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// Post tweet
app.post('/api/twitter/tweet', async (req, res) => {
  const bearerToken = process.env.TWITTER_BEARER_TOKEN;
  const { text } = req.body;
  
  if (!bearerToken || bearerToken.includes('PLACEHOLDER')) {
    return res.status(503).json({ error: 'TWITTER_BEARER_TOKEN nicht konfiguriert' });
  }
  
  if (!text) {
    return res.status(400).json({ error: 'Tweet text is required' });
  }
  
  try {
    const response = await fetch('https://api.twitter.com/2/tweets', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${bearerToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text })
    });
    
    if (response.ok) {
      const tweetData = await response.json();
      res.json({ success: true, data: tweetData });
    } else {
      const error = await response.text();
      throw new Error(`Twitter API Error: ${response.status} - ${error}`);
    }
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// ============================================================
// INSTAGRAM BASIC DISPLAY API ENDPOINTS
// ============================================================

// Instagram user info
app.get('/api/instagram/me', async (req, res) => {
  const accessToken = process.env.INSTAGRAM_ACCESS_TOKEN;
  
  if (!accessToken || accessToken.includes('PLACEHOLDER')) {
    return res.status(503).json({ error: 'INSTAGRAM_ACCESS_TOKEN nicht konfiguriert' });
  }
  
  try {
    const response = await fetch(`https://graph.instagram.com/me?fields=id,username,account_type,media_count&access_token=${accessToken}`);
    
    if (response.ok) {
      const userData = await response.json();
      res.json({ success: true, data: userData });
    } else {
      throw new Error(`Instagram API Error: ${response.status}`);
    }
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// ── START ─────────────────────────────────────────────────────
// ── CRITICAL ERROR HANDLERS ───────────────────────────────────────
// Prevent server crashes from unhandled promise rejections
process.on('unhandledRejection', (reason, promise) => {
  console.error('❌ Unhandled Rejection at:', promise, 'reason:', reason);
  // Log but don't crash - continue serving requests
});

// Prevent server crashes from uncaught exceptions
process.on('uncaughtException', (error) => {
  console.error('❌ Uncaught Exception:', error);
  // Log error but try to keep server running
  // In production, you might want to gracefully shutdown here
  if (process.env.NODE_ENV === 'production') {
    console.error('🔴 Critical error in production - shutting down gracefully');
    process.exit(1);
  }
});

app.listen(PORT, () => {
  console.log(`\n🚀 AutoPilot Server läuft auf Port ${PORT}`);
  console.log(`📋 API Status: http://localhost:${PORT}/api/status`);
  console.log(`💚 Health:     http://localhost:${PORT}/api/health`);
  console.log(`\n✅ Konfiguriert:`);
  console.log(`   Claude AI:  ${process.env.ANTHROPIC_API_KEY ? '✅' : '❌'}`);
  console.log(`   Shopify:    ${TOK  ? '✅ '+SHOP  : '❌ fehlt'}`);
  console.log(`   GitHub:     ${GH_TOK ? '✅ '+GH_USER : '❌ fehlt'}`);
  console.log(`\n🛡️ Security: CSP enabled, CORS restricted, error handlers active`);
});

module.exports = app;
