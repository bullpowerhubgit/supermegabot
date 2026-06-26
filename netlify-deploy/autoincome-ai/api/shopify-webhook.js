// Shopify Order Webhook Handler
// GET ?secret=... → registers orders/create webhook at Shopify (idempotent)
// POST (no secret) → receives Shopify order payload → adds buyer to Klaviyo + Telegram alert

const SHOPIFY_DOMAIN  = process.env.SHOPIFY_SHOP_DOMAIN;
const SHOPIFY_TOKEN   = process.env.SHOPIFY_ADMIN_API_TOKEN;
const SHOPIFY_VER     = process.env.SHOPIFY_API_VERSION || '2024-04';
const KLAVIYO_KEY     = process.env.KLAVIYO_API_KEY;
const TELEGRAM_BOT    = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT   = process.env.TELEGRAM_CHAT_ID;
const KLAVIYO_LIST_ID = 'Xwxq6V';
const WEBHOOK_URL     = 'https://autoincome-ai.vercel.app/api/shopify-webhook';

async function sendTelegram(msg) {
  if (!TELEGRAM_BOT || !TELEGRAM_CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML' }),
    });
  } catch {}
}

async function addToKlaviyo(email, firstName, lastName, orderValue, productName) {
  if (!KLAVIYO_KEY || !email) return;
  const profileResp = await fetch('https://a.klaviyo.com/api/profiles/', {
    method: 'POST',
    headers: {
      Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`,
      revision: '2024-10-15',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      data: {
        type: 'profile',
        attributes: {
          email,
          first_name: firstName || '',
          last_name: lastName || '',
          properties: {
            shopify_order_value: parseFloat(orderValue || 0),
            shopify_product: productName || '',
            customer_type: 'shopify_buyer',
          },
        },
      },
    }),
    signal: AbortSignal.timeout(10000),
  });
  const profileData = await profileResp.json().catch(() => ({}));
  const profileId = profileData?.data?.id || profileData?.errors?.[0]?.meta?.duplicate_profile_id;
  if (!profileId) return;

  await fetch(`https://a.klaviyo.com/api/lists/${KLAVIYO_LIST_ID}/relationships/profiles/`, {
    method: 'POST',
    headers: {
      Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`,
      revision: '2024-10-15',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ data: [{ type: 'profile', id: profileId }] }),
    signal: AbortSignal.timeout(10000),
  });
}

export default async function handler(req, res) {
  if (req.method === 'POST') {
    // Shopify webhook POST — no auth guard (Shopify sends without secret)
    let order;
    try {
      order = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    } catch {
      return res.status(400).json({ error: 'invalid json' });
    }

    const email       = order?.email || order?.customer?.email;
    const firstName   = order?.customer?.first_name || '';
    const lastName    = order?.customer?.last_name || '';
    const totalPrice  = order?.total_price || '0.00';
    const product     = order?.line_items?.[0]?.title || 'Unbekannt';
    const orderId     = order?.order_number || order?.id || '';

    if (!email) return res.status(200).json({ ok: true, skipped: 'no email' });

    try {
      await addToKlaviyo(email, firstName, lastName, totalPrice, product);
      await sendTelegram(
        `🛍️ <b>Neue Shopify Bestellung!</b>\n` +
        `💰 €${parseFloat(totalPrice).toFixed(2)}\n` +
        `📦 ${product.substring(0, 60)}\n` +
        `👤 ${email}\n` +
        `🔢 Order #${orderId}`
      );
    } catch (err) {
      await sendTelegram(`⚠️ Shopify Webhook Fehler (Order #${orderId}): ${err.message.substring(0, 150)}`);
    }

    return res.status(200).json({ ok: true, email, orderId });
  }

  // GET — register webhook at Shopify (requires secret)
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== (process.env.CRON_SECRET || 'bullpower2026')) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  if (!SHOPIFY_DOMAIN || !SHOPIFY_TOKEN) {
    return res.status(200).json({ ok: false, error: 'Shopify ENV missing' });
  }

  const base = `https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}`;
  const shopifyHeaders = { 'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json' };

  try {
    const listResp = await fetch(`${base}/webhooks.json?topic=orders%2Fcreate`, {
      headers: shopifyHeaders,
      signal: AbortSignal.timeout(10000),
    });
    const listData = await listResp.json();
    const existing = (listData.webhooks || []).find(w => w.address === WEBHOOK_URL);

    if (existing) {
      return res.status(200).json({ ok: true, action: 'already_exists', id: existing.id });
    }

    const createResp = await fetch(`${base}/webhooks.json`, {
      method: 'POST',
      headers: shopifyHeaders,
      body: JSON.stringify({ webhook: { topic: 'orders/create', address: WEBHOOK_URL, format: 'json' } }),
      signal: AbortSignal.timeout(10000),
    });
    const createData = await createResp.json();

    if (!createData.webhook?.id) {
      throw new Error(`Webhook-Erstellung fehlgeschlagen: ${JSON.stringify(createData).substring(0, 200)}`);
    }

    await sendTelegram(`✅ Shopify Webhook registriert!\nID: ${createData.webhook.id}\nTopic: orders/create\nURL: ${WEBHOOK_URL}`);
    return res.status(200).json({ ok: true, action: 'registered', id: createData.webhook.id });
  } catch (err) {
    await sendTelegram(`❌ Shopify Webhook-Registrierung fehlgeschlagen: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }
}
