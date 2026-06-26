// DS24 Affiliate Performance Report — jeden Freitag 08:00 UTC via Vercel Cron
export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== (process.env.CRON_SECRET || 'bullpower2026')) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  const DS24_KEY    = process.env.DIGISTORE24_API_KEY;
  const TELEGRAM_BOT  = process.env.TELEGRAM_BOT_TOKEN;
  const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;

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

  if (!DS24_KEY) {
    await sendTelegram('⚠️ affiliate-report: DIGISTORE24_API_KEY fehlt in Vercel ENV!');
    return res.status(200).json({ ok: false, error: 'DS24_KEY missing' });
  }

  const now      = new Date();
  const weekAgo  = new Date(now - 7 * 24 * 60 * 60 * 1000);
  const todayStr = now.toISOString().slice(0, 10);
  const weekStr  = weekAgo.toISOString().slice(0, 10);
  const headers  = { 'X-DS-API-KEY': DS24_KEY };

  // ISO week number
  const jan1 = new Date(now.getFullYear(), 0, 1);
  const kw   = Math.ceil(((now - jan1) / 86400000 + jan1.getDay() + 1) / 7);

  let transactions = [];
  let listAffiliates = [];

  try {
    const r = await fetch(
      `https://www.digistore24.com/api/call/listTransactions/JSON/?from=${weekStr}&to=${todayStr}`,
      { headers, signal: AbortSignal.timeout(15000) }
    );
    const data = await r.json();
    transactions = data?.data?.orders || data?.data?.transactions || [];
  } catch (err) {
    await sendTelegram(`❌ affiliate-report: DS24 API Fehler: ${err.message.substring(0, 150)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }

  // Try listing all affiliates (optional endpoint)
  try {
    const rAff = await fetch(
      `https://www.digistore24.com/api/call/listAffiliates/JSON/`,
      { headers, signal: AbortSignal.timeout(10000) }
    );
    const affData = await rAff.json();
    listAffiliates = affData?.data?.affiliates || [];
  } catch {}

  // Build affiliate → name map from listAffiliates
  const affNameMap = {};
  for (const a of listAffiliates) {
    if (a.id) affNameMap[a.id] = a.name || a.email || `Affiliate #${a.id}`;
  }

  // Aggregate affiliate performance from transactions
  const affStats = {};
  for (const txn of transactions) {
    const affId   = txn.affiliate_id || txn.affiliateId || null;
    const revenue = parseFloat(txn.amount || txn.total_price || txn.order_amount || 0);
    if (!affId || revenue <= 0) continue;
    if (!affStats[affId]) affStats[affId] = { name: affNameMap[affId] || `ID ${affId}`, sales: 0, revenue: 0 };
    affStats[affId].sales++;
    affStats[affId].revenue += revenue;
  }

  const sorted = Object.values(affStats).sort((a, b) => b.sales - a.sales);
  const totalProvision = sorted.reduce((s, a) => s + a.revenue * 0.5, 0);
  const totalSales     = sorted.reduce((s, a) => s + a.sales, 0);

  const TIPS = [
    'Schreibe deinen Affiliates eine persönliche Dankes-Email — erhöht Loyalität um 40%.',
    'Teile einen neuen LinkedIn-Post in der Affiliate-Gruppe — gibt frischen Traffic.',
    'Erstelle 3 neue Social-Media-Vorlagen für Affiliates → mehr Shares.',
    'Biete Top-Affiliates (>5 Sales/Woche) einen Bonus-Provisionssatz an.',
    'Überprüfe ob alle Affiliate-Links auf der Danke-Seite korrekt weiterleiten.',
  ];
  const tip = TIPS[Math.floor(Math.random() * TIPS.length)];

  if (sorted.length === 0) {
    const msg =
      `🎯 <b>Affiliate-Report KW ${kw}</b>\n\n` +
      `Keine Affiliate-Aktivität diese Woche.\n\n` +
      `📌 <b>Tipp:</b> ${tip}\n\n` +
      `Affiliate-Programm: https://autoincome-ai.vercel.app/affiliate.html`;
    await sendTelegram(msg);
    return res.status(200).json({ ok: true, kw, affiliates: 0, totalSales: 0, totalProvision: 0 });
  }

  const lines = sorted.slice(0, 10).map(a =>
    `• ${a.name} — ${a.sales} Verkäufe · €${(a.revenue * 0.5).toFixed(2)} Provision`
  ).join('\n');

  const superAff = sorted.filter(a => a.sales >= 3).map(a => a.name);
  const superBlock = superAff.length > 0
    ? `\n\n⭐ <b>Super-Affiliates (≥3 Sales):</b> ${superAff.join(', ')}\n→ Persönlich anschreiben + Bonus anbieten!`
    : '';

  const msg =
    `🎯 <b>Affiliate-Report KW ${kw}</b>\n\n` +
    `<b>Aktive Affiliates diese Woche:</b>\n${lines}\n\n` +
    `📊 Gesamt: <b>${sorted.length} Affiliates · ${totalSales} Verkäufe · €${totalProvision.toFixed(2)} Provision</b>` +
    superBlock +
    `\n\n📌 <b>Tipp:</b> ${tip}`;

  await sendTelegram(msg);

  return res.status(200).json({
    ok: true,
    kw,
    affiliates: sorted.length,
    totalSales,
    totalProvision,
    top: sorted.slice(0, 5),
  });
}
