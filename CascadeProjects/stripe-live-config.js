/**
 * 💰 STRIPE LIVE KONFIGURATION
 * Kein Test-Modus. Echtes Geld. Jetzt.
 * 
 * Erforderliche .env Variablen:
 * STRIPE_SECRET_KEY=sk_live_...
 * STRIPE_PUBLISHABLE_KEY=pk_live_...
 * STRIPE_WEBHOOK_SECRET=whsec_...
 */

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

// ── PRODUKT-PLÄNE (LIVE) ──
const PLANS = {
  starter: {
    name: 'Shopify Automation Starter',
    description: '1 Store, 100 Produkte, Basis-Automatisierung',
    price: 2900, // 29,00€ in Cent
    currency: 'eur',
    interval: 'month',
    features: [
      '1 Shopify Store',
      '100 Produkte',
      'Auto-Import',
      'Preis-Anpassung',
      'E-Mail Support'
    ]
  },
  pro: {
    name: 'Shopify Automation Pro',
    description: '3 Stores, unbegrenzte Produkte, AI Features',
    price: 7900, // 79,00€ in Cent
    currency: 'eur',
    interval: 'month',
    features: [
      '3 Shopify Stores',
      'Unbegrenzte Produkte',
      'Auto-Import + AI',
      'SEO-Optimierung',
      'Social Media Auto-Post',
      'Analytics Dashboard',
      'Priority Support'
    ]
  },
  agency: {
    name: 'Shopify Automation Agency',
    description: '10 Stores, White-Label, Vollautomatisierung',
    price: 19900, // 199,00€ in Cent
    currency: 'eur',
    interval: 'month',
    features: [
      '10 Shopify Stores',
      'Unbegrenzte Produkte',
      'Voll-Automatisierung',
      'White-Label Dashboard',
      'API Zugang',
      'Custom Integration',
      'Dedicated Support',
      'Team-Management'
    ]
  }
};

// ── STRIPE PRODUKTE ERSTELLEN (Einmalig ausführen) ──
async function createStripeProducts() {
  console.log('🏗️ Erstelle Stripe LIVE Produkte...\n');
  
  for (const [key, plan] of Object.entries(PLANS)) {
    try {
      // Produkt erstellen
      const product = await stripe.products.create({
        name: plan.name,
        description: plan.description,
        metadata: {
          tier: key,
          max_stores: key === 'starter' ? '1' : key === 'pro' ? '3' : '10'
        }
      });
      
      // Preis erstellen (Subscription)
      const price = await stripe.prices.create({
        product: product.id,
        unit_amount: plan.price,
        currency: plan.currency,
        recurring: { interval: plan.interval },
        metadata: { tier: key }
      });
      
      console.log(`✅ ${plan.name}`);
      console.log(`   Produkt ID: ${product.id}`);
      console.log(`   Preis ID: ${price.id}`);
      console.log(`   Preis: ${(plan.price / 100).toFixed(2)}€/${plan.interval}\n`);
      
    } catch (error) {
      console.error(`❌ Fehler bei ${plan.name}:`, error.message);
    }
  }
}

// ── CHECKOUT SESSION ERSTELLEN ──
async function createCheckoutSession(tier, customerEmail, successUrl, cancelUrl) {
  const plan = PLANS[tier];
  if (!plan) throw new Error('Ungültiger Plan');
  
  // Preis-ID aus Stripe holen (muss zuvor erstellt worden sein)
  const prices = await stripe.prices.list({ 
    lookup_keys: [`${tier}_monthly`],
    limit: 1 
  });
  
  const priceId = prices.data[0]?.id;
  if (!priceId) throw new Error('Preis nicht gefunden');
  
  const session = await stripe.checkout.sessions.create({
    customer_email: customerEmail,
    payment_method_types: ['card', 'sepa_debit'],
    line_items: [{
      price: priceId,
      quantity: 1
    }],
    mode: 'subscription',
    success_url: successUrl,
    cancel_url: cancelUrl,
    subscription_data: {
      trial_period_days: 14, // 14 Tage kostenlos testen
      metadata: { tier }
    },
    metadata: { tier, source: 'rudibot_dashboard' }
  });
  
  return session;
}

// ── WEBHOOK HANDLER ──
async function handleWebhookEvent(event) {
  const { type, data } = event;
  
  switch (type) {
    case 'checkout.session.completed':
      await handleSubscriptionCreated(data.object);
      break;
      
    case 'invoice.payment_succeeded':
      await handlePaymentSuccess(data.object);
      break;
      
    case 'invoice.payment_failed':
      await handlePaymentFailed(data.object);
      break;
      
    case 'customer.subscription.deleted':
      await handleSubscriptionCanceled(data.object);
      break;
      
    default:
      console.log(`📋 Unbehandeltes Event: ${type}`);
  }
}

async function handleSubscriptionCreated(session) {
  const { customer_email, subscription, metadata } = session;
  
  // Supabase aktualisieren
  console.log(`🎉 NEUER KUNDE!`);
  console.log(`   E-Mail: ${customer_email}`);
  console.log(`   Plan: ${metadata.tier}`);
  console.log(`   Subscription: ${subscription}`);
  
  // Telegram Benachrichtigung
  await sendTelegramAlert(`
💰 NEUER VERKAUF!
Plan: ${metadata.tier.toUpperCase()}
Kunde: ${customer_email}
Betrag: ${PLANS[metadata.tier].price / 100}€/Monat
  `);
  
  // Supabase User erstellen
  // await supabase.from('subscriptions').insert({...})
}

async function handlePaymentSuccess(invoice) {
  console.log(`✅ Zahlung erfolgreich: ${invoice.id}`);
  // Rechnung senden, Zugang verlängern
}

async function handlePaymentFailed(invoice) {
  console.log(`⚠️ Zahlung fehlgeschlagen: ${invoice.id}`);
  
  // Kunde informieren
  await sendTelegramAlert(`
⚠️ ZAHLUNG FEHLGESCHLAGEN!
Customer: ${invoice.customer_email}
Betrag: ${invoice.amount_due / 100}€
Status: ${invoice.status}
  `);
}

async function handleSubscriptionCanceled(subscription) {
  console.log(`❌ Subscription gekündigt: ${subscription.id}`);
  
  // Zugang sperren
  await sendTelegramAlert(`
❌ KÜNDIGUNG!
Customer: ${subscription.customer}
Grund: ${subscription.cancellation_details?.reason || 'Nicht angegeben'}
  `);
}

// ── TELEGRAM ALERT ──
async function sendTelegramAlert(message) {
  const botToken = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  
  if (!botToken || !chatId) return;
  
  try {
    await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        text: message,
        parse_mode: 'HTML'
      })
    });
  } catch (e) {
    console.error('Telegram Alert fehlgeschlagen:', e);
  }
}

// ── REVENUE REPORT ──
async function getRevenueReport(days = 30) {
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);
  
  const charges = await stripe.charges.list({
    created: { gte: Math.floor(startDate.getTime() / 1000) },
    limit: 100
  });
  
  const total = charges.data.reduce((sum, charge) => sum + charge.amount, 0);
  const count = charges.data.length;
  
  return {
    period: `${days} Tage`,
    total_revenue: total / 100,
    total_charges: count,
    average_order: count > 0 ? (total / count / 100).toFixed(2) : 0,
    currency: 'EUR'
  };
}

module.exports = {
  createStripeProducts,
  createCheckoutSession,
  handleWebhookEvent,
  getRevenueReport,
  PLANS
};

// ── CLI AUSFÜHRUNG ──
if (require.main === module) {
  createStripeProducts();
}
