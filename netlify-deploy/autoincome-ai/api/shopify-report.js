// Shopify Daily Sales Report — täglich 07:05 UTC via Vercel Cron
export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== (process.env.CRON_SECRET || 'bullpower2026')) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  const SHOPIFY_DOMAIN = process.env.SHOPIFY_SHOP_DOMAIN;
  const SHOPIFY_TOKEN  = process.env.SHOPIFY_ADMIN_API_TOKEN;
  const SHOPIFY_VER    = process.env.SHOPIFY_API_VERSION || '2024-04';
  const TELEGRAM_BOT   = process.env.TELEGRAM_BOT_TOKEN;
  const TELEGRAM_CHAT  = process.env.TELEGRAM_CHAT_ID;

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

  if (!SHOPIFY_DOMAIN || !SHOPIFY_TOKEN) {
    await sendTelegram('⚠️ shopify-report: SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlt in Vercel ENV!');
    return res.status(200).json({ ok: false, error: 'Shopify ENV missing' });
  }

  const base = `https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}`;
  const headers = { 'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json' };

  async function shopifyGet(path) {
    const r = await fetch(`${base}${path}`, { headers, signal: AbortSignal.timeout(15000) });
    if (!r.ok) throw new Error(`Shopify ${r.status}: ${path}`);
    return r.json();
  }

  try {
    const now = new Date();
    const yesterday = new Date(now - 24 * 60 * 60 * 1000).toISOString();
    const weekAgo   = new Date(now - 7  * 24 * 60 * 60 * 1000).toISOString();
    const monthStart = now.toISOString().slice(0, 7) + '-01T00:00:00Z';

    const [todayData, weekData, shopData, productData] = await Promise.all([
      shopifyGet(`/orders.json?status=any&created_at_min=${yesterday}&limit=250`),
      shopifyGet(`/orders.json?status=any&created_at_min=${weekAgo}&limit=250`),
      shopifyGet('/shop.json'),
      shopifyGet('/products/count.json?status=active'),
    ]);

    const paidOnly = (orders) => (orders || []).filter(o => o.financial_status === 'paid');
    const sumRevenue = (orders) => orders.reduce((s, o) => s + parseFloat(o.total_price || 0), 0);

    const todayOrders  = paidOnly(todayData.orders);
    const weekOrders   = paidOnly(weekData.orders);
    const todayRev     = sumRevenue(todayOrders);
    const weekRev      = sumRevenue(weekOrders);
    const currency     = shopData.shop?.currency || 'EUR';
    const productCount = productData.count || 0;

    // Monthly revenue from week data filtered by month start
    const monthOrders  = weekOrders.filter(o => o.created_at >= monthStart);
    const monthRev     = sumRevenue(monthOrders);
    const monthPct     = Math.min(100, Math.round((monthRev / 1000) * 100));

    // Top products today
    const itemMap = {};
    for (const order of todayOrders) {
      for (const item of order.line_items || []) {
        const key = item.title;
        if (!itemMap[key]) itemMap[key] = { price: parseFloat(item.price || 0), qty: 0 };
        itemMap[key].qty += item.quantity || 1;
      }
    }
    const topItems = Object.entries(itemMap)
      .sort((a, b) => b[1].qty - a[1].qty)
      .slice(0, 3)
      .map(([name, v]) => `• ${name.substring(0, 40)} — ${currency} ${v.price.toFixed(2)} (${v.qty}×)`)
      .join('\n');

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

    return res.status(200).json({
      ok: true,
      today:  { orders: todayOrders.length, revenue: todayRev },
      week:   { orders: weekOrders.length,  revenue: weekRev  },
      month:  { orders: monthOrders.length, revenue: monthRev },
      products: productCount,
    });
  } catch (err) {
    await sendTelegram(`❌ shopify-report Fehler: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }
}
