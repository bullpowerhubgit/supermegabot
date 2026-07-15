/**
 * Stripe Connect SaaS Platform — ineedit.com.co / AIITEC
 * Express backend: Connected Accounts, Onboarding, Products, Checkout
 * Port: 3005
 */
import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import Stripe from 'stripe';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 3005;
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;
const FEE_PERCENT = parseInt(process.env.PLATFORM_FEE_PERCENT || '10');

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', {
  apiVersion: '2024-06-20',
});

// ── Middleware ────────────────────────────────────────────────────────────────
app.use(cors());
// Webhook braucht raw body — VOR express.json()
app.post('/webhook', express.raw({ type: 'application/json' }), handleWebhook);
app.use(express.json());
app.use(express.static(join(__dirname, 'public')));

// ── 1. Connected Account erstellen ───────────────────────────────────────────
app.post('/api/account', async (req, res) => {
  try {
    const account = await stripe.accounts.create({
      controller: {
        stripe_dashboard: { type: 'none' },
        fees: { payer: 'application' },
        losses: { payments: 'application' },
        requirement_collection: 'application',
      },
      capabilities: {
        transfers: { requested: true },
        card_payments: { requested: true },
      },
      country: 'DE',
    });
    res.json({ accountId: account.id });
  } catch (err) {
    console.error('create-account error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── 2. Account-Status abrufen ─────────────────────────────────────────────────
app.get('/api/account/:accountId/status', async (req, res) => {
  try {
    const account = await stripe.accounts.retrieve(req.params.accountId);
    res.json({
      accountId: account.id,
      chargesEnabled: account.charges_enabled,
      payoutsEnabled: account.payouts_enabled,
      detailsSubmitted: account.details_submitted,
      requirements: account.requirements,
      email: account.email,
      businessProfile: account.business_profile,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 3. Account-Link für Onboarding ────────────────────────────────────────────
app.post('/api/account-link', async (req, res) => {
  const { accountId } = req.body;
  if (!accountId) return res.status(400).json({ error: 'accountId fehlt' });
  try {
    const link = await stripe.accountLinks.create({
      account: accountId,
      refresh_url: `${APP_URL}/refresh?accountId=${accountId}`,
      return_url: `${APP_URL}/return?accountId=${accountId}`,
      type: 'account_onboarding',
    });
    res.json({ url: link.url });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 4. Produkt für verbundenes Konto erstellen ────────────────────────────────
app.post('/api/create-product', async (req, res) => {
  const { accountId, productName, productDescription, productPrice } = req.body;
  if (!accountId || !productName || !productPrice) {
    return res.status(400).json({ error: 'accountId, productName, productPrice erforderlich' });
  }
  try {
    const product = await stripe.products.create(
      {
        name: productName,
        description: productDescription || '',
      },
      { stripeAccount: accountId }
    );
    const price = await stripe.prices.create(
      {
        product: product.id,
        unit_amount: productPrice,
        currency: 'eur',
      },
      { stripeAccount: accountId }
    );
    res.json({
      productId: product.id,
      priceId: price.id,
      productName: product.name,
      amount: price.unit_amount,
      currency: price.currency,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 5. Produkte eines Kontos abrufen ──────────────────────────────────────────
app.get('/api/products/:accountId', async (req, res) => {
  try {
    const products = await stripe.products.list(
      { active: true, limit: 20 },
      { stripeAccount: req.params.accountId }
    );
    const withPrices = await Promise.all(
      products.data.map(async (p) => {
        const prices = await stripe.prices.list(
          { product: p.id, active: true, limit: 1 },
          { stripeAccount: req.params.accountId }
        );
        return {
          id: p.id,
          name: p.name,
          description: p.description,
          price: prices.data[0] || null,
        };
      })
    );
    res.json({ products: withPrices });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 6. Checkout-Session erstellen ─────────────────────────────────────────────
app.post('/api/create-checkout-session', async (req, res) => {
  const { accountId, priceId, productName } = req.body;
  if (!accountId || !priceId) {
    return res.status(400).json({ error: 'accountId und priceId erforderlich' });
  }
  try {
    // Preis abrufen um Betrag für Platform-Fee zu berechnen
    const price = await stripe.prices.retrieve(priceId, { stripeAccount: accountId });
    const platformFee = Math.round((price.unit_amount || 0) * FEE_PERCENT / 100);

    const session = await stripe.checkout.sessions.create(
      {
        mode: 'payment',
        line_items: [{ price: priceId, quantity: 1 }],
        payment_intent_data: {
          application_fee_amount: platformFee,
        },
        success_url: `${APP_URL}/done?session_id={CHECKOUT_SESSION_ID}&account=${accountId}`,
        cancel_url: `${APP_URL}/storefront?account=${accountId}`,
        locale: 'de',
      },
      { stripeAccount: accountId }
    );
    res.json({ url: session.url });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 7. Alle verbundenen Konten abrufen (Platform-Übersicht) ───────────────────
app.get('/api/accounts', async (req, res) => {
  try {
    const accounts = await stripe.accounts.list({ limit: 50 });
    res.json({
      accounts: accounts.data.map(a => ({
        id: a.id,
        email: a.email,
        chargesEnabled: a.charges_enabled,
        detailsSubmitted: a.details_submitted,
        country: a.country,
        created: a.created,
        businessName: a.business_profile?.name || '',
      }))
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 8. Plattform-Umsatz (Einnahmen der Plattform) ────────────────────────────
app.get('/api/platform/revenue', async (req, res) => {
  try {
    const charges = await stripe.applicationFees.list({ limit: 100 });
    const total = charges.data.reduce((sum, f) => sum + f.amount, 0);
    res.json({
      total_cents: total,
      total_eur: (total / 100).toFixed(2),
      fees: charges.data.map(f => ({
        id: f.id,
        amount: f.amount,
        currency: f.currency,
        created: f.created,
        account: f.account,
      }))
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 9. Webhook ────────────────────────────────────────────────────────────────
async function handleWebhook(req, res) {
  const sig = req.headers['stripe-signature'];
  let event;
  try {
    event = stripe.webhooks.constructEvent(
      req.body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET || ''
    );
  } catch (err) {
    console.error('Webhook-Signatur ungültig:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  console.log(`Webhook: ${event.type}`);

  switch (event.type) {
    case 'account.updated': {
      const account = event.data.object;
      console.log(`Account ${account.id}: charges_enabled=${account.charges_enabled}`);
      break;
    }
    case 'checkout.session.completed': {
      const session = event.data.object;
      console.log(`Zahlung OK: ${session.id} — ${session.amount_total} ${session.currency}`);
      // TODO: Telegram-Notification, DB-Eintrag, etc.
      break;
    }
    case 'payment_intent.succeeded': {
      const pi = event.data.object;
      console.log(`PaymentIntent ${pi.id}: ${pi.amount} ${pi.currency}`);
      break;
    }
  }

  res.json({ received: true });
}

// ── 10. Webhook-Endpoints verwalten (Stripe API) ──────────────────────────────
app.get('/api/webhooks', async (req, res) => {
  try {
    const endpoints = await stripe.webhookEndpoints.list({ limit: 20 });
    res.json({ webhooks: endpoints.data });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

app.post('/api/webhooks/setup', async (req, res) => {
  // Registriert den eigenen /webhook Endpoint bei Stripe — einmalig beim Deploy aufrufen
  const webhookUrl = `${APP_URL}/webhook`;
  try {
    // Prüfe ob schon ein Endpoint mit dieser URL existiert
    const existing = await stripe.webhookEndpoints.list({ limit: 50 });
    const found = existing.data.find(e => e.url === webhookUrl && e.status === 'enabled');
    if (found) {
      return res.json({ already_registered: true, id: found.id, url: found.url });
    }
    const endpoint = await stripe.webhookEndpoints.create({
      url: webhookUrl,
      enabled_events: [
        'account.updated',
        'checkout.session.completed',
        'payment_intent.succeeded',
        'payment_intent.payment_failed',
        'application_fee.created',
        'customer.subscription.created',
        'customer.subscription.deleted',
        'charge.succeeded',
        'charge.failed',
      ],
      description: 'SuperMegaBot Connect Platform Webhook',
      metadata: { platform: 'supermegabot', env: process.env.NODE_ENV || 'production' },
    });
    res.json({
      registered: true,
      id: endpoint.id,
      url: endpoint.url,
      secret: endpoint.secret,
      note: 'WICHTIG: secret als STRIPE_WEBHOOK_SECRET in Railway ENV setzen!',
    });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

app.delete('/api/webhooks/:id', async (req, res) => {
  try {
    const deleted = await stripe.webhookEndpoints.del(req.params.id);
    res.json({ deleted: true, id: deleted.id });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

// ── 11. Customers mit Metadata ─────────────────────────────────────────────────
app.post('/api/customer', async (req, res) => {
  const { email, name, accountId, metadata = {} } = req.body;
  if (!email) return res.status(400).json({ error: 'email erforderlich' });
  try {
    const customer = await stripe.customers.create(
      {
        email,
        name: name || '',
        metadata: { platform: 'supermegabot', ...metadata },
      },
      accountId ? { stripeAccount: accountId } : {}
    );
    res.json({ customerId: customer.id, email: customer.email });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

// ── 12. Health-Check ──────────────────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'stripe-connect-saas',
    platform_fee_percent: FEE_PERCENT,
    stripe_configured: !!process.env.STRIPE_SECRET_KEY,
    timestamp: new Date().toISOString(),
  });
});

// ── Frontend SPA (alle anderen Routen) ───────────────────────────────────────
app.get('*', (req, res) => {
  res.sendFile(join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, async () => {
  console.log(`🚀 Stripe Connect SaaS läuft auf Port ${PORT}`);
  console.log(`📊 Platform-Fee: ${FEE_PERCENT}%`);
  console.log(`🔑 Stripe: ${process.env.STRIPE_SECRET_KEY ? '✅ konfiguriert' : '❌ STRIPE_SECRET_KEY fehlt'}`);
  console.log(`🌐 App URL: ${APP_URL}`);

  // Webhook automatisch registrieren wenn APP_URL gesetzt und kein localhost
  if (process.env.STRIPE_SECRET_KEY && APP_URL && !APP_URL.includes('localhost')) {
    try {
      const webhookUrl = `${APP_URL}/webhook`;
      const existing = await stripe.webhookEndpoints.list({ limit: 50 });
      const found = existing.data.find(e => e.url === webhookUrl && e.status === 'enabled');
      if (!found) {
        const endpoint = await stripe.webhookEndpoints.create({
          url: webhookUrl,
          enabled_events: [
            'account.updated', 'checkout.session.completed',
            'payment_intent.succeeded', 'application_fee.created',
            'customer.subscription.created', 'customer.subscription.deleted',
          ],
          description: 'SuperMegaBot Connect Auto-Setup',
        });
        console.log(`🔔 Webhook auto-registriert: ${endpoint.id}`);
        console.log(`⚠️  WEBHOOK SECRET (einmalig!): ${endpoint.secret}`);
        console.log(`    → In Railway ENV setzen: STRIPE_WEBHOOK_SECRET=${endpoint.secret}`);
      } else {
        console.log(`🔔 Webhook bereits registriert: ${found.id}`);
      }
    } catch (e) {
      console.error('Webhook Auto-Setup Fehler:', e.message);
    }
  }
});
