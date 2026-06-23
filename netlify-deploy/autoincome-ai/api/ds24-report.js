// DS24 Daily Revenue Report — täglich 07:00 UTC via Vercel Cron
export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  const CRON_SECRET = process.env.CRON_SECRET || 'bullpower2026';
  if (secret !== CRON_SECRET) return res.status(401).json({ error: 'Unauthorized' });

  const DS24_KEY = process.env.DIGISTORE24_API_KEY;
  const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
  const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;

  const today = new Date().toISOString().slice(0, 10);
  const r = await fetch(
    `https://www.digistore24.com/api/call/listTransactions/JSON/?from=2025-01-01&to=${today}`,
    { headers: { 'X-DS-API-KEY': DS24_KEY }, signal: AbortSignal.timeout(15000) }
  );

  if (!r.ok) {
    return res.status(500).json({ error: 'DS24 API failed', status: r.status });
  }

  const data = await r.json();
  const summary = data?.data?.summary || {};
  const eur = summary?.amounts?.EUR || {};
  const count = eur.count || 0;
  const total = eur.total_amount || 0;

  const emoji = total >= 500 ? '🟢' : total >= 100 ? '🟡' : '🔴';
  const date = new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC';

  const milestones = [5, 10, 25, 50, 100];
  const milestone = milestones.find((m) => count === m);
  const milestoneMsg = milestone ? `\n\n🎉 <b>MEILENSTEIN: ${milestone} Verkäufe!</b>` : '';

  const msg =
    `${emoji} <b>DS24 Daily Report</b> [${date}]\n\n` +
    `💰 Revenue: <b>€${total.toFixed(2)}</b>\n` +
    `🛒 Transaktionen: <b>${count}</b>\n` +
    `🎯 Ziel: €1.000/Monat\n` +
    `📈 Fortschritt: ${Math.min(100, Math.round((total / 1000) * 100))}%` +
    milestoneMsg;

  if (TELEGRAM_TOKEN && TELEGRAM_CHAT) {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML' }),
    });
  }

  return res.json({ ok: true, total, count });
}
