// Combined Shopify handler:
// GET ?type=report&secret=... → daily Shopify report (cron 07:05 UTC)
// GET ?type=webhook&secret=... → register orders/create webhook at Shopify (idempotent)
// POST (no auth) → receive Shopify order webhook → Klaviyo + Telegram

const SHOPIFY_DOMAIN  = process.env.SHOPIFY_SHOP_DOMAIN;
const SHOPIFY_TOKEN   = process.env.SHOPIFY_ADMIN_API_TOKEN;
const SHOPIFY_VER     = process.env.SHOPIFY_API_VERSION || '2024-04';
const KLAVIYO_KEY     = process.env.KLAVIYO_API_KEY;
const TELEGRAM_BOT    = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT   = process.env.TELEGRAM_CHAT_ID;
const CRON_SECRET     = process.env.CRON_SECRET || 'bullpower2026';
const KLAVIYO_LIST_ID = 'Xwxq6V';
const WEBHOOK_URL     = 'https://autoincome-ai.vercel.app/api/shopify';

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
    headers: { Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`, revision: '2024-10-15', 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: { type: 'profile', attributes: { email, first_name: firstName || '', last_name: lastName || '', properties: { shopify_order_value: parseFloat(orderValue || 0), shopify_product: productName || '', customer_type: 'shopify_buyer' } } } }),
    signal: AbortSignal.timeout(10000),
  });
  const profileData = await profileResp.json().catch(() => ({}));
  const profileId = profileData?.data?.id || profileData?.errors?.[0]?.meta?.duplicate_profile_id;
  if (!profileId) return;
  await fetch(`https://a.klaviyo.com/api/lists/${KLAVIYO_LIST_ID}/relationships/profiles/`, {
    method: 'POST',
    headers: { Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`, revision: '2024-10-15', 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: [{ type: 'profile', id: profileId }] }),
    signal: AbortSignal.timeout(10000),
  });
}

async function handleWebhookPost(req, res) {
  let order;
  try {
    order = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  } catch {
    return res.status(400).json({ error: 'invalid json' });
  }

  const email      = order?.email || order?.customer?.email;
  const firstName  = order?.customer?.first_name || '';
  const lastName   = order?.customer?.last_name || '';
  const totalPrice = order?.total_price || '0.00';
  const product    = order?.line_items?.[0]?.title || 'Unbekannt';
  const orderId    = order?.order_number || order?.id || '';

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

async function handleRegisterWebhook(res) {
  if (!SHOPIFY_DOMAIN || !SHOPIFY_TOKEN) return res.status(200).json({ ok: false, error: 'Shopify ENV missing' });
  const base = `https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}`;
  const h = { 'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json' };
  try {
    const listResp = await fetch(`${base}/webhooks.json?topic=orders%2Fcreate`, { headers: h, signal: AbortSignal.timeout(10000) });
    const listData = await listResp.json();
    const existing = (listData.webhooks || []).find(w => w.address === WEBHOOK_URL);
    if (existing) return res.status(200).json({ ok: true, action: 'already_exists', id: existing.id });
    const createResp = await fetch(`${base}/webhooks.json`, {
      method: 'POST', headers: h,
      body: JSON.stringify({ webhook: { topic: 'orders/create', address: WEBHOOK_URL, format: 'json' } }),
      signal: AbortSignal.timeout(10000),
    });
    const createData = await createResp.json();
    if (!createData.webhook?.id) throw new Error(`Webhook-Erstellung fehlgeschlagen: ${JSON.stringify(createData).substring(0, 200)}`);
    await sendTelegram(`✅ Shopify Webhook registriert!\nID: ${createData.webhook.id}\nTopic: orders/create\nURL: ${WEBHOOK_URL}`);
    return res.status(200).json({ ok: true, action: 'registered', id: createData.webhook.id });
  } catch (err) {
    await sendTelegram(`❌ Shopify Webhook-Registrierung fehlgeschlagen: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }
}

async function handleDailyReport(res) {
  if (!SHOPIFY_DOMAIN || !SHOPIFY_TOKEN) {
    await sendTelegram('⚠️ shopify-report: SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlt in Vercel ENV!');
    return res.status(200).json({ ok: false, error: 'Shopify ENV missing' });
  }
  const base = `https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}`;
  const h = { 'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json' };
  const shopifyGet = async (path) => {
    const r = await fetch(`${base}${path}`, { headers: h, signal: AbortSignal.timeout(15000) });
    if (!r.ok) throw new Error(`Shopify ${r.status}: ${path}`);
    return r.json();
  };
  try {
    const now = new Date();
    const yesterday  = new Date(now - 24 * 60 * 60 * 1000).toISOString();
    const weekAgo    = new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString();
    const monthStart = now.toISOString().slice(0, 7) + '-01T00:00:00Z';
    const [todayData, weekData, shopData, productData] = await Promise.all([
      shopifyGet(`/orders.json?status=any&created_at_min=${yesterday}&limit=250`),
      shopifyGet(`/orders.json?status=any&created_at_min=${weekAgo}&limit=250`),
      shopifyGet('/shop.json'),
      shopifyGet('/products/count.json?status=active'),
    ]);
    const paidOnly   = (orders) => (orders || []).filter(o => o.financial_status === 'paid');
    const sumRevenue = (orders) => orders.reduce((s, o) => s + parseFloat(o.total_price || 0), 0);
    const todayOrders = paidOnly(todayData.orders);
    const weekOrders  = paidOnly(weekData.orders);
    const todayRev    = sumRevenue(todayOrders);
    const weekRev     = sumRevenue(weekOrders);
    const currency    = shopData.shop?.currency || 'EUR';
    const productCount = productData.count || 0;
    const monthOrders = weekOrders.filter(o => o.created_at >= monthStart);
    const monthRev    = sumRevenue(monthOrders);
    const monthPct    = Math.min(100, Math.round((monthRev / 1000) * 100));
    const itemMap = {};
    for (const order of todayOrders) {
      for (const item of order.line_items || []) {
        if (!itemMap[item.title]) itemMap[item.title] = { price: parseFloat(item.price || 0), qty: 0 };
        itemMap[item.title].qty += item.quantity || 1;
      }
    }
    const topItems = Object.entries(itemMap).sort((a, b) => b[1].qty - a[1].qty).slice(0, 3)
      .map(([name, v]) => `• ${name.substring(0, 40)} — ${currency} ${v.price.toFixed(2)} (${v.qty}×)`).join('\n');
    const date = now.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
    const emoji = todayRev > 0 ? '🟢' : '🔴';
    const topBlock = topItems ? `\n\n🏆 Top-Artikel heute:\n${topItems}` : '';
    const msg =
      `${emoji} <b>Shopify Daily Report</b> [${date}]\n\n` +
      `📅 Heute: <b>${todayOrders.length} Bestellungen · ${currency} ${todayRev.toFixed(2)}</b>\n` +
      `📊 Diese Woche: <b>${weekOrders.length} Bestellungen · ${currency} ${weekRev.toFixed(2)}</b>\n` +
      `🏪 Aktive Produkte: <b>${productCount.toLocaleString('de-DE')}</b>` +
      topBlock +
      `\n\n🎯 Monatsziel: ${currency} 1.000\n📈 Fortschritt: ${monthPct}%`;
    await sendTelegram(msg);
    return res.status(200).json({ ok: true, today: { orders: todayOrders.length, revenue: todayRev }, week: { orders: weekOrders.length, revenue: weekRev }, month: { orders: monthOrders.length, revenue: monthRev }, products: productCount });
  } catch (err) {
    await sendTelegram(`❌ shopify-report Fehler: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }
}

export default async function handler(req, res) {
  if (req.method === 'POST') return handleWebhookPost(req, res);

  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const type = req.query.type || 'report';
  if (type === 'webhook') return handleRegisterWebhook(res);
  return handleDailyReport(res);
}
