// Fiverr + Upwork Gig Notifier + Proposal Sender
// Cron: täglich 08:00 UTC
// Fiverr: kein öffentliches API → Browser-Automation via Telegram-Erinnerung
// Upwork: Freelancer-Profil + Jobs suchen via API
// Benötigt: UPWORK_CLIENT_ID, UPWORK_CLIENT_SECRET, UPWORK_ACCESS_TOKEN

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const UPWORK_TOKEN = process.env.UPWORK_ACCESS_TOKEN;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';

// Gig-Beschreibungen für Fiverr (Rudolf postet 1x/Woche manuell oder via Computer-Use)
const FIVERR_GIGS = [
  {
    title: 'I will set up a complete AI automation system for your German online business',
    description: `I will set up the SuperMegaBot AI Automation System for your online business:

✅ LinkedIn auto-poster (Mon/Wed/Fri, 9am)
✅ Email marketing automation (Klaviyo sequences)
✅ Digistore24 digital product setup
✅ Telegram revenue reports (daily 7am)
✅ SEO blog system (32+ articles)
✅ 1-click Railway deployment

Perfect for: German-speaking online entrepreneurs, affiliate marketers, digital product sellers.

Delivery: 3-5 days
Requirements: Your API credentials (I'll guide you through each one)

⭐ This is the same system that generated €111 passive income in 4 months.`,
    price: 97,
    deliveryDays: 5,
    category: 'AI & Automation',
  },
  {
    title: 'I will create a German AI income blueprint and set up your passive income funnel',
    description: `Complete done-for-you passive income setup for the German market:

✅ AI Income Machine Blueprint (90-day plan)
✅ Digistore24 product setup + listing
✅ Klaviyo email sequence (4 automated emails)
✅ Landing page optimization
✅ LinkedIn content strategy (German)

The German market has 85% LESS competition than English for AI content. Now is the time.

Results: My system generated €111 in 4 months with ZERO ads.

Delivery: 5-7 days`,
    price: 147,
    deliveryDays: 7,
    category: 'Digital Marketing',
  },
];

// Upwork job search keywords (Rudolf soll darauf Proposals schicken)
const UPWORK_KEYWORDS = [
  'KI Automatisierung deutsch',
  'LinkedIn Automation German',
  'Digistore24 setup',
  'passive income automation',
  'email marketing Klaviyo',
  'AI online business german',
];

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

async function searchUpworkJobs(keyword) {
  if (!UPWORK_TOKEN) return null;
  // Upwork Freelancer API — job search
  const r = await fetch(`https://www.upwork.com/api/profiles/v2/search/jobs.json?q=${encodeURIComponent(keyword)}&paging=0;5`, {
    headers: {
      Authorization: `Bearer ${UPWORK_TOKEN}`,
    },
  });
  if (!r.ok) return null;
  const data = await r.json();
  return data.jobs?.job || [];
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const results = [];
  const today = new Date().toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' });

  // --- FIVERR: Tägliche Erinnerung + Gig Text ---
  // Fiverr hat keine öffentliche API für Gig-Erstellung
  // Jeden Montag: Gig-Update-Erinnerung senden
  const dayOfWeek = new Date().getUTCDay();
  if (dayOfWeek === 1) {
    const gigIdx = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000)) % FIVERR_GIGS.length;
    const gig = FIVERR_GIGS[gigIdx];
    await sendTelegram(
      `🟢 <b>Fiverr Wochentask (${today}):</b>\n\n` +
      `Gig prüfen/aktualisieren:\n` +
      `<b>"${gig.title}"</b>\n` +
      `Preis: $${gig.price} | ${gig.deliveryDays} Tage\n\n` +
      `Fiverr.com → Gigs → "Update" klicken um Sichtbarkeit zu erhöhen\n` +
      `(Frische Gigs ranken besser)`
    );
    results.push({ platform: 'fiverr', action: 'weekly_reminder_sent' });
  }

  // --- UPWORK: Jobs suchen und Tipp senden ---
  if (UPWORK_TOKEN) {
    const keywordIdx = new Date().getUTCDate() % UPWORK_KEYWORDS.length;
    const keyword = UPWORK_KEYWORDS[keywordIdx];
    const jobs = await searchUpworkJobs(keyword);

    if (jobs && jobs.length > 0) {
      const jobList = jobs.slice(0, 3).map((j, i) =>
        `${i + 1}. ${j.title || 'Job'} — $${j.budget?.amount || '?'}`
      ).join('\n');
      await sendTelegram(
        `💼 <b>Upwork Jobs (${keyword}):</b>\n${jobList}\n\nupwork.com/nx/find-work/`
      );
      results.push({ platform: 'upwork', keyword, found: jobs.length });
    }
  } else {
    // Täglich: Erinnerung welche Keywords man suchen soll
    const keywordIdx = new Date().getUTCDate() % UPWORK_KEYWORDS.length;
    await sendTelegram(
      `💼 <b>Upwork Tipp (${today}):</b>\n` +
      `Suche: "${UPWORK_KEYWORDS[keywordIdx]}"\n` +
      `→ 2-3 Proposals mit SuperMegaBot-Angebot\n` +
      `→ upwork.com/nx/find-work/?q=${encodeURIComponent(UPWORK_KEYWORDS[keywordIdx])}\n\n` +
      `Aktiviere Upwork API für automatische Suche:\n` +
      `vercel env add UPWORK_ACCESS_TOKEN production`
    );
    results.push({ platform: 'upwork', action: 'daily_tip_sent', keyword: UPWORK_KEYWORDS[keywordIdx] });
  }

  return res.status(200).json({ ok: true, results, date: today });
}
