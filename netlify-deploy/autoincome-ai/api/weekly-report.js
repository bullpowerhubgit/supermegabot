// Weekly KPI Report — jeden Montag 07:30 UTC via Vercel Cron
export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== (process.env.CRON_SECRET || 'bullpower2026')) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  const DS24_KEY       = process.env.DIGISTORE24_API_KEY;
  const KLAVIYO_KEY    = process.env.KLAVIYO_API_KEY;
  const SHOPIFY_DOMAIN = process.env.SHOPIFY_SHOP_DOMAIN;
  const SHOPIFY_TOKEN  = process.env.SHOPIFY_ADMIN_API_TOKEN;
  const SHOPIFY_VER    = process.env.SHOPIFY_API_VERSION || '2024-04';
  const SUPABASE_URL   = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
  const SUPABASE_KEY   = process.env.SUPABASE_SERVICE_KEY;
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

  const now        = new Date();
  const weekAgo    = new Date(now - 7 * 24 * 60 * 60 * 1000);
  const monthStart = now.toISOString().slice(0, 7) + '-01';
  const weekAgoStr = weekAgo.toISOString().slice(0, 10);
  const todayStr   = now.toISOString().slice(0, 10);

  // ISO week number
  const jan1 = new Date(now.getFullYear(), 0, 1);
  const kw   = Math.ceil(((now - jan1) / 86400000 + jan1.getDay() + 1) / 7);

  const ds24Headers   = { 'X-DS-API-KEY': DS24_KEY || '' };
  const shopifyHeaders = SHOPIFY_DOMAIN && SHOPIFY_TOKEN
    ? { 'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json' }
    : null;

  // Fetch all data in parallel, individual failures return null
  const [ds24Week, ds24Month, klaviyoList, shopifyOrders, supaTotalRaw, supaWeekRaw] = await Promise.allSettled([
    DS24_KEY
      ? fetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=${weekAgoStr}&to=${todayStr}`, { headers: ds24Headers, signal: AbortSignal.timeout(15000) }).then(r => r.json())
      : Promise.resolve(null),
    DS24_KEY
      ? fetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=${monthStart}&to=${todayStr}`, { headers: ds24Headers, signal: AbortSignal.timeout(15000) }).then(r => r.json())
      : Promise.resolve(null),
    KLAVIYO_KEY
      ? fetch('https://a.klaviyo.com/api/lists/Xwxq6V/', { headers: { Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`, revision: '2024-10-15' }, signal: AbortSignal.timeout(10000) }).then(r => r.json())
      : Promise.resolve(null),
    shopifyHeaders
      ? fetch(`https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}/orders.json?status=any&created_at_min=${weekAgo.toISOString()}&limit=250`, { headers: shopifyHeaders, signal: AbortSignal.timeout(15000) }).then(r => r.json())
      : Promise.resolve(null),
    SUPABASE_KEY
      ? fetch(`${SUPABASE_URL}/rest/v1/seo_content?select=count&published=eq.true`, { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}`, Prefer: 'count=exact' }, signal: AbortSignal.timeout(10000) }).then(r => ({ count: r.headers.get('Content-Range')?.split('/')?.[1] || '?' }))
      : Promise.resolve(null),
    SUPABASE_KEY
      ? fetch(`${SUPABASE_URL}/rest/v1/seo_content?select=slug&published=eq.true&created_at=gte.${weekAgo.toISOString()}`, { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` }, signal: AbortSignal.timeout(10000) }).then(r => r.json())
      : Promise.resolve([]),
  ]);

  const v = (settled) => settled.status === 'fulfilled' ? settled.value : null;

  // DS24 week
  const ds24WeekEur    = v(ds24Week)?.data?.summary?.amounts?.EUR || {};
  const weekRevDs24    = ds24WeekEur.total_amount || 0;
  const weekCountDs24  = ds24WeekEur.count || 0;

  // DS24 month
  const ds24MonthEur   = v(ds24Month)?.data?.summary?.amounts?.EUR || {};
  const monthRevDs24   = ds24MonthEur.total_amount || 0;
  const monthCountDs24 = ds24MonthEur.count || 0;
  const monthPct       = Math.min(100, Math.round((monthRevDs24 / 1000) * 100));

  // Klaviyo
  const subCount = v(klaviyoList)?.data?.attributes?.profile_count ?? '?';

  // Shopify
  const shopOrders     = (v(shopifyOrders)?.orders || []).filter(o => o.financial_status === 'paid');
  const shopRevWeek    = shopOrders.reduce((s, o) => s + parseFloat(o.total_price || 0), 0);
  const shopCountWeek  = shopOrders.length;

  // Supabase Blog
  const totalArticles = v(supaTotalRaw)?.count || '?';
  const newArticles   = Array.isArray(v(supaWeekRaw)) ? v(supaWeekRaw).length : '?';

  // Auto-commentary
  const totalWeekRev = weekRevDs24 + shopRevWeek;
  const fazit = totalWeekRev >= 250
    ? '🟢 Starke Woche! Kurs stimmt ✅'
    : totalWeekRev >= 100
    ? '🟡 Gute Woche — weiter pushen!'
    : totalWeekRev >= 50
    ? '🟠 Ausbaufähig — Affiliate-Kampagne launchen!'
    : '🔴 Stagnation ⚠️ — Neuen Traffic-Kanal aktivieren!';

  const date   = now.toISOString().slice(0, 10);
  const ds24Block  = DS24_KEY
    ? `\n💰 <b>DS24 Revenue:</b>\n  Diese Woche: <b>€${weekRevDs24.toFixed(2)}</b> (${weekCountDs24} Verkäufe)\n  Dieser Monat: <b>€${monthRevDs24.toFixed(2)}</b> (${monthCountDs24} Verkäufe)\n  Ziel €1.000: <b>${monthPct}%</b>`
    : '\n💰 DS24: Key nicht gesetzt';
  const shopBlock  = shopifyHeaders
    ? `\n\n🛍️ <b>Shopify:</b>\n  Bestellungen: ${shopCountWeek}\n  Revenue: €${shopRevWeek.toFixed(2)}`
    : '';
  const klavBlock  = KLAVIYO_KEY ? `\n\n📧 <b>Klaviyo:</b> ${subCount} Subscriber` : '';
  const blogBlock  = SUPABASE_KEY ? `\n\n📝 <b>SEO-Blog:</b> ${totalArticles} Artikel | ${newArticles} neue diese Woche` : '';

  const msg =
    `📊 <b>WOCHENBERICHT KW ${kw}</b> [${date}]` +
    ds24Block + shopBlock + klavBlock + blogBlock +
    `\n\n🎯 <b>Fazit:</b> ${fazit}`;

  await sendTelegram(msg);

  return res.status(200).json({
    ok: true,
    kw,
    ds24: { weekRev: weekRevDs24, weekCount: weekCountDs24, monthRev: monthRevDs24 },
    shopify: { weekCount: shopCountWeek, weekRev: shopRevWeek },
    klaviyo: { subscribers: subCount },
    blog: { total: totalArticles, newThisWeek: newArticles },
  });
}
