// Combined Reports: DS24 Daily (?type=daily), Weekly KPI (?type=weekly), Affiliate (?type=affiliate)
// Crons: daily 07:00 (daily), Mon 07:30 (weekly), Fri 08:00 (affiliate)

const CRON_SECRET = process.env.CRON_SECRET || 'bullpower2026';

async function sendTelegram(msg) {
  const BOT = process.env.TELEGRAM_BOT_TOKEN;
  const CHAT = process.env.TELEGRAM_CHAT_ID;
  if (!BOT || !CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${BOT}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: CHAT, text: msg, parse_mode: 'HTML' }),
    });
  } catch {}
}

async function handleDaily(res) {
  const DS24_KEY = process.env.DIGISTORE24_API_KEY;
  const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
  const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;

  if (!DS24_KEY) {
    if (TELEGRAM_TOKEN && TELEGRAM_CHAT) {
      await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: '❌ DS24 Report: DIGISTORE24_API_KEY fehlt in Vercel ENV!', parse_mode: 'HTML' }),
      });
    }
    return res.status(200).json({ ok: false, error: 'DIGISTORE24_API_KEY missing' });
  }

  const today = new Date().toISOString().slice(0, 10);
  const monthStart = today.slice(0, 7) + '-01';

  const [rAll, rMonth] = await Promise.all([
    fetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=2025-01-01&to=${today}`,
      { headers: { 'X-DS-API-KEY': DS24_KEY }, signal: AbortSignal.timeout(15000) }),
    fetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=${monthStart}&to=${today}`,
      { headers: { 'X-DS-API-KEY': DS24_KEY }, signal: AbortSignal.timeout(15000) }),
  ]);

  if (!rAll.ok) return res.status(500).json({ error: 'DS24 API failed', status: rAll.status });

  const data = await rAll.json();
  const eur = data?.data?.summary?.amounts?.EUR || {};
  const count = eur.count || 0;
  const total = eur.total_amount || 0;

  let monthTotal = 0, monthCount = 0;
  if (rMonth.ok) {
    const mEur = (await rMonth.json())?.data?.summary?.amounts?.EUR || {};
    monthTotal = mEur.total_amount || 0;
    monthCount = mEur.count || 0;
  }

  const emoji = monthTotal >= 500 ? '🟢' : monthTotal >= 100 ? '🟡' : '🔴';
  const date = new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
  const milestones = [5, 10, 25, 50, 100];
  const milestone = milestones.find((m) => count === m);
  const milestoneMsg = milestone ? `\n\n🎉 <b>MEILENSTEIN: ${milestone} Verkäufe gesamt!</b>` : '';

  const msg =
    `${emoji} <b>DS24 Daily Report</b> [${date}]\n\n` +
    `📅 Diesen Monat: <b>€${monthTotal.toFixed(2)}</b> (${monthCount} Verkäufe)\n` +
    `📊 Gesamt: <b>€${total.toFixed(2)}</b> (${count} Verkäufe)\n` +
    `🎯 Monatsziel: €1.000\n` +
    `📈 Fortschritt: ${Math.min(100, Math.round((monthTotal / 1000) * 100))}%` +
    milestoneMsg;

  if (TELEGRAM_TOKEN && TELEGRAM_CHAT) {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML' }),
    });
  }
  return res.json({ ok: true, total, count });
}

async function handleWeekly(res) {
  const DS24_KEY       = process.env.DIGISTORE24_API_KEY;
  const KLAVIYO_KEY    = process.env.KLAVIYO_API_KEY;
  const SHOPIFY_DOMAIN = process.env.SHOPIFY_SHOP_DOMAIN;
  const SHOPIFY_TOKEN  = process.env.SHOPIFY_ADMIN_API_TOKEN;
  const SHOPIFY_VER    = process.env.SHOPIFY_API_VERSION || '2024-04';
  const SUPABASE_URL   = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
  const SUPABASE_KEY   = process.env.SUPABASE_SERVICE_KEY;

  const now        = new Date();
  const weekAgo    = new Date(now - 7 * 24 * 60 * 60 * 1000);
  const monthStart = now.toISOString().slice(0, 7) + '-01';
  const weekAgoStr = weekAgo.toISOString().slice(0, 10);
  const todayStr   = now.toISOString().slice(0, 10);
  const jan1 = new Date(now.getFullYear(), 0, 1);
  const kw   = Math.ceil(((now - jan1) / 86400000 + jan1.getDay() + 1) / 7);

  const ds24Headers    = { 'X-DS-API-KEY': DS24_KEY || '' };
  const shopifyHeaders = SHOPIFY_DOMAIN && SHOPIFY_TOKEN
    ? { 'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json' }
    : null;

  const [ds24Week, ds24Month, klaviyoList, shopifyOrders, supaTotalRaw, supaWeekRaw] = await Promise.allSettled([
    DS24_KEY ? fetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=${weekAgoStr}&to=${todayStr}`, { headers: ds24Headers, signal: AbortSignal.timeout(15000) }).then(r => r.json()) : Promise.resolve(null),
    DS24_KEY ? fetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=${monthStart}&to=${todayStr}`, { headers: ds24Headers, signal: AbortSignal.timeout(15000) }).then(r => r.json()) : Promise.resolve(null),
    KLAVIYO_KEY ? fetch('https://a.klaviyo.com/api/lists/Xwxq6V/', { headers: { Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`, revision: '2024-10-15' }, signal: AbortSignal.timeout(10000) }).then(r => r.json()) : Promise.resolve(null),
    shopifyHeaders ? fetch(`https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}/orders.json?status=any&created_at_min=${weekAgo.toISOString()}&limit=250`, { headers: shopifyHeaders, signal: AbortSignal.timeout(15000) }).then(r => r.json()) : Promise.resolve(null),
    SUPABASE_KEY ? fetch(`${SUPABASE_URL}/rest/v1/seo_content?select=count&published=eq.true`, { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}`, Prefer: 'count=exact' }, signal: AbortSignal.timeout(10000) }).then(r => ({ count: r.headers.get('Content-Range')?.split('/')?.[1] || '?' })) : Promise.resolve(null),
    SUPABASE_KEY ? fetch(`${SUPABASE_URL}/rest/v1/seo_content?select=slug&published=eq.true&created_at=gte.${weekAgo.toISOString()}`, { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` }, signal: AbortSignal.timeout(10000) }).then(r => r.json()) : Promise.resolve([]),
  ]);

  const v = (s) => s.status === 'fulfilled' ? s.value : null;
  const ds24WeekEur   = v(ds24Week)?.data?.summary?.amounts?.EUR || {};
  const weekRevDs24   = ds24WeekEur.total_amount || 0;
  const weekCountDs24 = ds24WeekEur.count || 0;
  const ds24MonthEur  = v(ds24Month)?.data?.summary?.amounts?.EUR || {};
  const monthRevDs24  = ds24MonthEur.total_amount || 0;
  const monthCountDs24 = ds24MonthEur.count || 0;
  const monthPct      = Math.min(100, Math.round((monthRevDs24 / 1000) * 100));
  const subCount      = v(klaviyoList)?.data?.attributes?.profile_count ?? '?';
  const shopOrders    = (v(shopifyOrders)?.orders || []).filter(o => o.financial_status === 'paid');
  const shopRevWeek   = shopOrders.reduce((s, o) => s + parseFloat(o.total_price || 0), 0);
  const shopCountWeek = shopOrders.length;
  const totalArticles = v(supaTotalRaw)?.count || '?';
  const newArticles   = Array.isArray(v(supaWeekRaw)) ? v(supaWeekRaw).length : '?';
  const totalWeekRev  = weekRevDs24 + shopRevWeek;
  const fazit = totalWeekRev >= 250 ? '🟢 Starke Woche! Kurs stimmt ✅' : totalWeekRev >= 100 ? '🟡 Gute Woche — weiter pushen!' : totalWeekRev >= 50 ? '🟠 Ausbaufähig — Affiliate-Kampagne launchen!' : '🔴 Stagnation ⚠️ — Neuen Traffic-Kanal aktivieren!';

  const date = now.toISOString().slice(0, 10);
  const msg =
    `📊 <b>WOCHENBERICHT KW ${kw}</b> [${date}]` +
    (DS24_KEY ? `\n💰 <b>DS24 Revenue:</b>\n  Diese Woche: <b>€${weekRevDs24.toFixed(2)}</b> (${weekCountDs24} Verkäufe)\n  Dieser Monat: <b>€${monthRevDs24.toFixed(2)}</b> (${monthCountDs24} Verkäufe)\n  Ziel €1.000: <b>${monthPct}%</b>` : '\n💰 DS24: Key nicht gesetzt') +
    (shopifyHeaders ? `\n\n🛍️ <b>Shopify:</b>\n  Bestellungen: ${shopCountWeek}\n  Revenue: €${shopRevWeek.toFixed(2)}` : '') +
    (KLAVIYO_KEY ? `\n\n📧 <b>Klaviyo:</b> ${subCount} Subscriber` : '') +
    (SUPABASE_KEY ? `\n\n📝 <b>SEO-Blog:</b> ${totalArticles} Artikel | ${newArticles} neue diese Woche` : '') +
    `\n\n🎯 <b>Fazit:</b> ${fazit}`;

  await sendTelegram(msg);
  return res.status(200).json({ ok: true, kw, ds24: { weekRev: weekRevDs24, monthRev: monthRevDs24 }, shopify: { weekCount: shopCountWeek, weekRev: shopRevWeek }, klaviyo: { subscribers: subCount }, blog: { total: totalArticles, newThisWeek: newArticles } });
}

async function handleAffiliate(res) {
  const DS24_KEY = process.env.DIGISTORE24_API_KEY;
  if (!DS24_KEY) {
    await sendTelegram('⚠️ affiliate-report: DIGISTORE24_API_KEY fehlt in Vercel ENV!');
    return res.status(200).json({ ok: false, error: 'DS24_KEY missing' });
  }

  const now = new Date();
  const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
  const todayStr = now.toISOString().slice(0, 10);
  const weekStr  = weekAgo.toISOString().slice(0, 10);
  const headers  = { 'X-DS-API-KEY': DS24_KEY };
  const jan1 = new Date(now.getFullYear(), 0, 1);
  const kw   = Math.ceil(((now - jan1) / 86400000 + jan1.getDay() + 1) / 7);

  let transactions = [], listAffiliates = [];
  try {
    const r = await fetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=${weekStr}&to=${todayStr}`, { headers, signal: AbortSignal.timeout(15000) });
    const data = await r.json();
    transactions = data?.data?.orders || data?.data?.transactions || [];
  } catch (err) {
    await sendTelegram(`❌ affiliate-report: DS24 API Fehler: ${err.message.substring(0, 150)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }
  try {
    const rAff = await fetch(`https://www.digistore24.com/api/call/listAffiliates/JSON/`, { headers, signal: AbortSignal.timeout(10000) });
    listAffiliates = (await rAff.json())?.data?.affiliates || [];
  } catch {}

  const affNameMap = {};
  for (const a of listAffiliates) { if (a.id) affNameMap[a.id] = a.name || a.email || `Affiliate #${a.id}`; }

  const affStats = {};
  for (const txn of transactions) {
    const affId = txn.affiliate_id || txn.affiliateId || null;
    const revenue = parseFloat(txn.amount || txn.total_price || txn.order_amount || 0);
    if (!affId || revenue <= 0) continue;
    if (!affStats[affId]) affStats[affId] = { name: affNameMap[affId] || `ID ${affId}`, sales: 0, revenue: 0 };
    affStats[affId].sales++;
    affStats[affId].revenue += revenue;
  }

  const sorted = Object.values(affStats).sort((a, b) => b.sales - a.sales);
  const totalProvision = sorted.reduce((s, a) => s + a.revenue * 0.5, 0);
  const totalSales = sorted.reduce((s, a) => s + a.sales, 0);
  const TIPS = ['Schreibe deinen Affiliates eine persönliche Dankes-Email — erhöht Loyalität um 40%.', 'Teile einen neuen LinkedIn-Post in der Affiliate-Gruppe — gibt frischen Traffic.', 'Erstelle 3 neue Social-Media-Vorlagen für Affiliates → mehr Shares.', 'Biete Top-Affiliates (>5 Sales/Woche) einen Bonus-Provisionssatz an.', 'Überprüfe ob alle Affiliate-Links auf der Danke-Seite korrekt weiterleiten.'];
  const tip = TIPS[Math.floor(Math.random() * TIPS.length)];

  if (sorted.length === 0) {
    await sendTelegram(`🎯 <b>Affiliate-Report KW ${kw}</b>\n\nKeine Affiliate-Aktivität diese Woche.\n\n📌 <b>Tipp:</b> ${tip}\n\nAffiliate-Programm: https://autoincome-ai.vercel.app/affiliate.html`);
    return res.status(200).json({ ok: true, kw, affiliates: 0, totalSales: 0, totalProvision: 0 });
  }

  const lines = sorted.slice(0, 10).map(a => `• ${a.name} — ${a.sales} Verkäufe · €${(a.revenue * 0.5).toFixed(2)} Provision`).join('\n');
  const superAff = sorted.filter(a => a.sales >= 3).map(a => a.name);
  const superBlock = superAff.length > 0 ? `\n\n⭐ <b>Super-Affiliates (≥3 Sales):</b> ${superAff.join(', ')}\n→ Persönlich anschreiben + Bonus anbieten!` : '';

  await sendTelegram(`🎯 <b>Affiliate-Report KW ${kw}</b>\n\n<b>Aktive Affiliates diese Woche:</b>\n${lines}\n\n📊 Gesamt: <b>${sorted.length} Affiliates · ${totalSales} Verkäufe · €${totalProvision.toFixed(2)} Provision</b>${superBlock}\n\n📌 <b>Tipp:</b> ${tip}`);
  return res.status(200).json({ ok: true, kw, affiliates: sorted.length, totalSales, totalProvision, top: sorted.slice(0, 5) });
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const type = req.query.type || 'daily';
  if (type === 'weekly') return handleWeekly(res);
  if (type === 'affiliate') return handleAffiliate(res);
  return handleDaily(res);
}
