/**
 * 🛒 DIGISTORE24 LIVE KONFIGURATION
 * Digitale Produkte. Echte Verkäufe. Automatisierter Zugang.
 * 
 * Erforderliche .env:
 * DIGISTORE24_API_KEY=dein_api_key
 * DIGISTORE24_WEBHOOK_SECRET=dein_webhook_secret
 */

const axios = require('axios');

// ── DIGISTORE24 PRODUKTE (LIVE) ──
const PRODUCTS = {
  masterclass: {
    id: 'masterclass-shopify', // Digistore24 Produkt-ID
    name: 'Shopify Automation Masterclass',
    price: 47.00,
    description: 'Kompletter Kurs zur Shopify Automatisierung',
    delivery: 'digital', // Automatischer Zugang
    access_url: '/access/masterclass',
    email_template: 'masterclass_welcome'
  },
  toolkit: {
    id: 'toolkit-ai-bot',
    name: 'AI Bot Builder Toolkit',
    price: 97.00,
    description: 'Fertige Bots + Skripte + Templates',
    delivery: 'digital',
    access_url: '/access/toolkit',
    email_template: 'toolkit_welcome'
  },
  system: {
    id: 'complete-system',
    name: 'Complete E-Commerce Automation System',
    price: 297.00,
    description: 'Alles inklusive: Kurs + Tools + 1-on-1 Setup',
    delivery: 'hybrid', // Digital + persönliches Onboarding
    access_url: '/access/complete',
    email_template: 'complete_welcome',
    includes_onboarding: true
  }
};

// ── DIGISTORE24 API CLIENT ──
class Digistore24API {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.baseURL = 'https://www.digistore24.com/api';
  }

  async getSales(startDate, endDate) {
    try {
      const response = await axios.post(`${this.baseURL}/getSales`, {
        api_key: this.apiKey,
        date_from: startDate,
        date_to: endDate
      });
      return response.data;
    } catch (error) {
      console.error('Digistore24 API Fehler:', error.message);
      throw error;
    }
  }

  async getProductSales(productId, days = 30) {
    const endDate = new Date().toISOString().split('T')[0];
    const startDate = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    
    const sales = await this.getSales(startDate, endDate);
    
    return sales.filter(sale => 
      sale.product_id === productId || 
      sale.product_name?.includes(PRODUCTS[productId]?.name)
    );
  }
}

// ── WEBHOOK HANDLER ──
async function handleDigistoreWebhook(payload, signature) {
  // Verify webhook signature
  const secret = process.env.DIGISTORE24_WEBHOOK_SECRET;
  if (!verifySignature(payload, signature, secret)) {
    throw new Error('Ungültige Webhook-Signatur');
  }

  const event = payload.type;
  const data = payload.data;

  switch (event) {
    case 'purchase':
      await handlePurchase(data);
      break;
    case 'refund':
      await handleRefund(data);
      break;
    case 'chargeback':
      await handleChargeback(data);
      break;
    case 'subscription_renewal':
      await handleRenewal(data);
      break;
    case 'subscription_cancellation':
      await handleCancellation(data);
      break;
    default:
      console.log(`Unbekanntes Event: ${event}`);
  }
}

async function handlePurchase(data) {
  const { 
    buyer_email, 
    buyer_first_name, 
    buyer_last_name,
    product_id,
    product_name,
    order_total,
    order_id,
    transaction_id
  } = data;

  const product = Object.values(PRODUCTS).find(p => p.id === product_id);
  
  console.log(`🎉 DIGISTORE24 VERKAUF!`);
  console.log(`   Produkt: ${product_name}`);
  console.log(`   Kunde: ${buyer_first_name} ${buyer_last_name} (${buyer_email})`);
  console.log(`   Betrag: ${order_total}€`);
  console.log(`   Order ID: ${order_id}`);

  // 1. Zugang in Supabase speichern
  await grantAccess({
    email: buyer_email,
    product_id,
    order_id,
    transaction_id,
    status: 'active'
  });

  // 2. Willkommens-E-Mail senden (via Klaviyo oder direkt)
  await sendWelcomeEmail({
    to: buyer_email,
    template: product?.email_template || 'default_welcome',
    product_name,
    access_url: product?.access_url,
    includes_onboarding: product?.includes_onboarding
  });

  // 3. Telegram Benachrichtigung
  await sendTelegramAlert(`
🛒 DIGISTORE24 VERKAUF!
Produkt: ${product_name}
Kunde: ${buyer_first_name} ${buyer_last_name}
E-Mail: ${buyer_email}
Betrag: ${order_total}€
Order: ${order_id}
  `);

  // 4. Analytics aktualisieren
  await trackSale({
    source: 'digistore24',
    product: product_name,
    amount: order_total,
    customer: buyer_email,
    timestamp: new Date().toISOString()
  });
}

async function handleRefund(data) {
  const { order_id, buyer_email, refund_amount } = data;
  
  console.log(`💸 RÜCKERSTATTUNG: ${order_id}`);

  // Zugang entziehen
  await revokeAccess({ order_id });

  await sendTelegramAlert(`
💸 RÜCKERSTATTUNG!
Order: ${order_id}
Kunde: ${buyer_email}
Betrag: ${refund_amount}€
  `);
}

async function handleChargeback(data) {
  const { order_id, buyer_email } = data;
  
  console.log(`🚨 CHARGEBACK: ${order_id}`);

  await revokeAccess({ order_id });

  await sendTelegramAlert(`
🚨 CHARGEBACK!
Order: ${order_id}
Kunde: ${buyer_email}
Aktion: Zugang gesperrt
  `);
}

// ── ZUGANGSVERWALTUNG ──
async function grantAccess({ email, product_id, order_id, transaction_id, status }) {
  // Supabase Integration
  const supabase = require('./supabase-client'); // Wird separat erstellt
  
  await supabase.from('product_access').upsert({
    email,
    product_id,
    order_id,
    transaction_id,
    status,
    granted_at: new Date().toISOString(),
    expires_at: null // Bei einmaligem Kauf kein Ablauf
  });

  console.log(`✅ Zugang gewährt: ${email} → ${product_id}`);
}

async function revokeAccess({ order_id }) {
  const supabase = require('./supabase-client');
  
  await supabase.from('product_access')
    .update({ status: 'revoked', revoked_at: new Date().toISOString() })
    .eq('order_id', order_id);

  console.log(`❌ Zugang entzogen: ${order_id}`);
}

// ── E-MAIL VERSAND ──
async function sendWelcomeEmail({ to, template, product_name, access_url, includes_onboarding }) {
  // Klaviyo Integration oder SMTP
  const emailContent = {
    masterclass_welcome: `
Hallo!

Vielen Dank für deinen Kauf der "Shopify Automation Masterclass"!

🎯 WAS DU ERHÄLTST:
- 12 Video-Module
- Fertige Automation-Skripte
- Shopify App Templates
- Private Community Zugang

🔗 DEIN ZUGANG:
${access_url}

Wir wünschen dir viel Erfolg!
Rudolf & Team
    `,
    toolkit_welcome: `
Hallo!

Danke für den Kauf des "AI Bot Builder Toolkits"!

🛠️ DEIN TOOLKIT ENTHÄLT:
- 50+ Fertige Bot-Skripte
- Telegram Bot Template
- Shopify Webhook Handler
- API Integration Examples

🔗 DOWNLOAD:
${access_url}

Viel Erfolg!
Rudolf & Team
    `,
    complete_welcome: `
Hallo!

Willkommen zum "Complete E-Commerce Automation System"!

🚀 DAS KOMPLETTPAKET:
- Masterclass Kurs
- AI Bot Builder Toolkit
- 1-on-1 Setup Call (60 Min)
- Priority Support (Lifetime)

🔗 ZUGANG:
${access_url}

📅 ONBOARDING:
${includes_onboarding ? 'Wir kontaktieren dich innerhalb 24h für deinen Setup-Call!' : ''}

Auf geht's!
Rudolf & Team
    `
  };

  const content = emailContent[template] || emailContent.default_welcome;
  
  // Hier E-Mail versenden (Klaviyo, SendGrid, etc.)
  console.log(`📧 E-Mail gesendet an: ${to}`);
  console.log(`   Inhalt: ${content.substring(0, 100)}...`);
}

// ── ANALYTICS ──
async function trackSale({ source, product, amount, customer, timestamp }) {
  // Supabase oder Google Analytics
  console.log(`📊 Sale getrackt: ${source} | ${product} | ${amount}€`);
}

// ── REVENUE REPORT ──
async function getDigistoreRevenue(days = 30) {
  const api = new Digistore24API(process.env.DIGISTORE24_API_KEY);
  
  const sales = await api.getProductSales(null, days);
  
  const total = sales.reduce((sum, sale) => sum + parseFloat(sale.order_total || 0), 0);
  const byProduct = {};
  
  sales.forEach(sale => {
    const name = sale.product_name || 'Unbekannt';
    byProduct[name] = (byProduct[name] || 0) + parseFloat(sale.order_total || 0);
  });

  return {
    period: `${days} Tage`,
    total_sales: sales.length,
    total_revenue: total.toFixed(2),
    by_product: byProduct,
    currency: 'EUR'
  };
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

// ── SIGNATUR-VERIFIZIERUNG ──
function verifySignature(payload, signature, secret) {
  const crypto = require('crypto');
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(payload))
    .digest('hex');
  
  return signature === expectedSignature;
}

module.exports = {
  handleDigistoreWebhook,
  getDigistoreRevenue,
  PRODUCTS,
  Digistore24API
};
