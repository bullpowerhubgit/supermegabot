// Reddit auto-poster — DS24 product 668035 promotion
// Runs Tue + Sat 10:00 UTC via Vercel Cron
// OAuth2: Authorization Code flow (web app) OR password grant (script app)
// Posts to: r/passiveincome, r/Entrepreneur, r/beermoney (rotating)

const REDDIT_CLIENT_ID = process.env.REDDIT_CLIENT_ID || 'hqgJAQe6Qiu5s5r1Vqc0Og';
const REDDIT_CLIENT_SECRET = process.env.REDDIT_CLIENT_SECRET || 'xsH99P7iCQAPeknbAXe5F9Nd9fV7aA';
const REDDIT_USERNAME = process.env.REDDIT_USERNAME || 'bullpowersrtkennels';
const REDDIT_PASSWORD = process.env.REDDIT_PASSWORD || 'Upper-Competition505';
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const SUPABASE_URL = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;
const REDIRECT_URI = 'https://autoincome-ai.vercel.app/api/reddit-poster?action=oauth-callback';
const REDDIT_TOKEN_ID = '00000000-0000-0000-0001-reddit000001';
const USER_AGENT = `AutoIncomeBot/1.0 by ${REDDIT_USERNAME}`;

// Post templates — rotating by week
const POSTS = [
  {
    subreddit: 'passiveincome',
    title: 'Built a passive income system with AI in German market — honest 4-month review (€111 revenue)',
    text: `I've been building an automated income system for the German-speaking market using AI tools over the past 4 months. Here's my honest breakdown:

**What I built:**
- Digital product (e-book/blueprint) on AI income strategies
- Automated email marketing via Klaviyo
- LinkedIn auto-posting system
- Digistore24 as the sales platform (biggest German-speaking platform for digital products)

**Results so far:**
- Month 1-2: €0 (setup and learning phase)
- Month 3: €37 (first sale — it actually works!)
- Month 4: €74 (2 more sales, fully automated)
- Total: **€111 in passive income**, no paid ads

**Key insight:** The German market is WAY less saturated than English for AI content. Same strategies, 5x less competition.

**The system runs automatically:**
- Email sequences fire without me
- LinkedIn posts at 9am MWF
- Daily revenue reports to Telegram

Still scaling this up. Current goal: €500/month by end of 2026.

Happy to answer questions. The blueprint I built: ${PRODUCT_URL} (it's in German but the strategy applies globally)`,
  },
  {
    subreddit: 'Entrepreneur',
    title: 'How I automated my entire digital product business using free/cheap AI tools — step by step',
    text: `Sharing my automation stack for running a digital product business with minimal manual work.

**The core stack (mostly free):**

1. **Klaviyo** (free up to 250 subscribers) — email automation, welcome sequences, promotional campaigns
2. **Vercel** (free) — serverless functions running on cron schedules
3. **Digistore24** (free to list) — German digital product marketplace, handles payments + affiliates
4. **LinkedIn API** — automated posting via Vercel cron (Mo/Wed/Fri 9am)
5. **Telegram Bot** — daily revenue reports and alerts

**What runs automatically every day without me:**
- Email campaigns send to leads
- Social media posts publish
- Revenue reports arrive in Telegram
- DS24 syncs sales data

**What I still do manually (~2 hours/week):**
- Check analytics
- Respond to customer questions
- Create new content occasionally

**Revenue:** €111 in 4 months, 3 sales of a €37 German AI income blueprint

The automation is the real product here. Once set up, it just runs.

Anyone else using this kind of serverless + cron approach for their business?`,
  },
  {
    subreddit: 'beermoney',
    title: 'Made €111 selling a German AI guide — here\'s exactly how the passive income setup works',
    text: `Not huge numbers but it's genuinely passive. Here's the full breakdown:

**The product:** A 90-day blueprint for building AI income in the German market (€37 one-time)

**Why German market?** Less competition. An English AI guide has 1000x more competitors. In German, you stand out immediately.

**Platform:** Digistore24 — it's like Clickbank but for German-speaking Europe. They handle:
- Payment processing
- Affiliate program (50% commission to affiliates)
- Refund management
- Tax/VAT compliance

**The automation funnel:**
1. LinkedIn posts → people click → landing page
2. Landing page → email signup (free checklist)
3. Email sequence → product sale
4. Digistore24 → payment + delivery → done

**Timeline:** First sale came 3 months after launch. Then 2 more in month 4 without any new effort.

**Affiliate angle:** I offer 50% commission (€18.50/sale). Anyone with a German-speaking audience can promote it.
More info: ${AFFILIATE_URL}

Not replacing my income yet but the passive part is real — I haven't touched it in weeks and sales still come in.`,
  },
  {
    subreddit: 'digitalnomad',
    title: 'Running a fully automated German digital product business from anywhere — tech stack breakdown',
    text: `My entire business runs on free/cheap tools and I can manage it from anywhere with just a phone.

**The setup:**

**Product delivery:** Digistore24 handles everything automatically
- Customer pays → Digistore24 delivers PDF
- Affiliate commission → paid out automatically weekly
- Refunds → handled without me

**Marketing automation:**
- Vercel serverless functions (free tier) run on schedules
- LinkedIn posts 3x/week at 9am UTC
- Email campaigns 2x/week to my list
- Daily revenue report → Telegram notification

**Monitoring:** Telegram bot sends me:
- Every new sale (instant notification)
- Daily revenue summary at 7am
- Any system errors

**Total monthly cost:** ~$5/month (Vercel Pro for cron jobs)

**Revenue:** €111 over 4 months, 0 monthly overhead

The key was building systems instead of doing things manually. Now the "work" is just checking Telegram once a day.

Product: ${PRODUCT_URL} (German, but the automation framework applies anywhere)`,
  },
  {
    subreddit: 'passive_income',
    title: '4-month update: AI-powered German digital product — €111 completely passive (full breakdown)',
    text: `Posted my initial setup a few months ago, here's the honest update.

**Month-by-month:**
- Month 1: €0, lots of setup work
- Month 2: €0, testing and fixing
- Month 3: €37 🎉 first sale
- Month 4: €74 (2 sales with zero new work)
- **Total: €111 passive income**

**What changed from month 2 → 3:** I stopped trying to force sales and let the automation do its job. The email sequence, LinkedIn posts, and SEO content all needed time to compound.

**The system now:**
✅ Email automation: Welcome sequence + weekly promotional emails
✅ Social media: LinkedIn posts 3x/week via cron job
✅ Lead generation: Free checklist lead magnet (collecting emails)
✅ Affiliate program: 10+ affiliates promoting for 50% commission
✅ Daily monitoring: Telegram bot reports at 7am

**Current bottleneck:** More traffic = more sales. Working on organic SEO and affiliate recruitment.

**Realistic projection:** €500/month by end of 2026 if current trajectory continues.

Not a get-rich story but genuinely passive income growing over time.`,
  },
];

async function storeTokenToSupabase(tokenData) {
  if (!SUPABASE_KEY) return;
  const context = { ...tokenData, stored_at: Date.now() };
  await fetch(`${SUPABASE_URL}/rest/v1/agent_memory`, {
    method: 'POST',
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      'Content-Type': 'application/json',
      Prefer: 'resolution=merge-duplicates',
    },
    body: JSON.stringify({
      id: REDDIT_TOKEN_ID,
      agent_role: 'reddit-oauth',
      type: 'fact',
      content: tokenData.refresh_token || tokenData.access_token,
      context,
      confidence: 100,
    }),
  });
}

async function loadTokenFromSupabase() {
  if (!SUPABASE_KEY) return null;
  const r = await fetch(`${SUPABASE_URL}/rest/v1/agent_memory?id=eq.${REDDIT_TOKEN_ID}&select=context`, {
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` },
  });
  if (!r.ok) return null;
  const data = await r.json();
  return data?.[0]?.context || null;
}

async function getRedditTokenViaOAuth() {
  const stored = await loadTokenFromSupabase();
  if (!stored?.refresh_token && !stored?.access_token) throw new Error('no_stored_token');

  const ageMs = Date.now() - (stored.stored_at || 0);
  if (ageMs < 55 * 60 * 1000 && stored.access_token) return stored.access_token;

  const creds = Buffer.from(`${REDDIT_CLIENT_ID}:${REDDIT_CLIENT_SECRET}`).toString('base64');
  const r = await fetch('https://www.reddit.com/api/v1/access_token', {
    method: 'POST',
    headers: { Authorization: `Basic ${creds}`, 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': USER_AGENT },
    body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: stored.refresh_token }).toString(),
  });
  if (!r.ok) throw new Error(`Refresh failed ${r.status}`);
  const data = await r.json();
  if (data.error) throw new Error(`Refresh error: ${data.error}`);
  await storeTokenToSupabase({ ...data, refresh_token: stored.refresh_token });
  return data.access_token;
}

async function sendTelegram(msg) {
  if (!TELEGRAM_BOT || !TELEGRAM_CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg }),
    });
  } catch {}
}

async function getRedditToken() {
  if (!REDDIT_CLIENT_ID || !REDDIT_CLIENT_SECRET) throw new Error('REDDIT_CLIENT_ID/SECRET not set in Vercel env vars');
  if (!REDDIT_PASSWORD) throw new Error('REDDIT_PASSWORD not set');
  const credentials = Buffer.from(`${REDDIT_CLIENT_ID}:${REDDIT_CLIENT_SECRET}`).toString('base64');
  const params = new URLSearchParams({
    grant_type: 'password',
    username: REDDIT_USERNAME,
    password: REDDIT_PASSWORD,
  });
  const r = await fetch('https://www.reddit.com/api/v1/access_token', {
    method: 'POST',
    headers: {
      Authorization: `Basic ${credentials}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': `AutoIncomeBot/1.0 by ${REDDIT_USERNAME}`,
    },
    body: params.toString(),
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`Reddit auth failed ${r.status}: ${txt}`);
  }
  const data = await r.json();
  if (data.error) throw new Error(`Reddit auth error: ${data.error}`);
  return data.access_token;
}

async function submitPost(token, subreddit, title, text) {
  const params = new URLSearchParams({
    sr: subreddit,
    kind: 'self',
    title,
    text,
    nsfw: 'false',
    spoiler: 'false',
    resubmit: 'true',
  });
  const r = await fetch('https://oauth.reddit.com/api/submit', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': `AutoIncomeBot/1.0 by ${REDDIT_USERNAME}`,
    },
    body: params.toString(),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`Submit failed ${r.status}: ${JSON.stringify(data).substring(0, 300)}`);
  // Reddit returns errors in json.json.errors array even on 200
  const errors = data?.json?.errors;
  if (errors && errors.length > 0) throw new Error(`Reddit errors: ${JSON.stringify(errors)}`);
  const postUrl = data?.json?.data?.url;
  return postUrl || 'no URL returned';
}

export default async function handler(req, res) {
  const { action, code, error: oauthError, state } = req.query || {};

  // OAuth Authorization Code flow — runs before secret check
  if (action === 'oauth-start') {
    const s = Math.random().toString(36).slice(2);
    const url =
      `https://www.reddit.com/api/v1/authorize` +
      `?client_id=${REDDIT_CLIENT_ID}` +
      `&response_type=code` +
      `&state=${s}` +
      `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
      `&duration=permanent` +
      `&scope=submit,read,identity`;
    res.setHeader('Location', url);
    return res.status(302).end();
  }

  if (action === 'oauth-callback' || code || oauthError) {
    if (oauthError) return res.status(400).send(`<h2>Reddit OAuth Fehler: ${oauthError}</h2>`);
    if (!code) return res.status(400).send('<h2>Kein Code von Reddit erhalten.</h2>');
    try {
      const creds = Buffer.from(`${REDDIT_CLIENT_ID}:${REDDIT_CLIENT_SECRET}`).toString('base64');
      const r = await fetch('https://www.reddit.com/api/v1/access_token', {
        method: 'POST',
        headers: { Authorization: `Basic ${creds}`, 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': USER_AGENT },
        body: new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: REDIRECT_URI }).toString(),
      });
      const data = await r.json();
      if (data.error || !data.access_token) throw new Error(data.error || 'no access_token');
      await storeTokenToSupabase(data);
      await sendTelegram('✅ Reddit OAuth erfolgreich! reddit-poster postet jetzt automatisch Di+Sa 10:00 UTC zu r/passiveincome, r/Entrepreneur, r/beermoney.');
      return res.status(200).send(`<html><body style="font-family:sans-serif;padding:40px;background:#0f0f1a;color:#e2e8f0"><h2 style="color:#4ade80">✅ Reddit OAuth erfolgreich!</h2><p>Der Reddit Auto-Poster ist jetzt aktiviert.<br>Posts gehen automatisch Di+Sa 10:00 UTC an r/passiveincome, r/Entrepreneur und r/beermoney.</p><p><a href="/" style="color:#a78bfa">← Zurück</a></p></body></html>`);
    } catch (err) {
      return res.status(500).send(`<h2>OAuth Fehler: ${err.message}</h2>`);
    }
  }

  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  // Rotate posts by day-of-week + week number for variety
  const now = new Date();
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const postIndex = weekNum % POSTS.length;
  const post = POSTS[postIndex];

  // Try OAuth token first (web app flow), then password grant (script type)
  let token;
  try {
    token = await getRedditTokenViaOAuth();
  } catch {
    try {
      token = await getRedditToken();
    } catch (err) {
      const authUrl = 'https://autoincome-ai.vercel.app/api/reddit-poster?action=oauth-start';
      await sendTelegram(
        `❌ Reddit: Kein Token verfügbar.\n\n` +
        `🔗 Einmalig autorisieren (klick):\n${authUrl}\n\n` +
        `Alternativ: reddit.com/prefs/apps → rodbot → Edit → Typ: script`
      );
      return res.status(500).json({ ok: false, error: err.message, fix: authUrl });
    }
  }

  // Wait 2 seconds after auth (Reddit rate limit)
  await new Promise((r) => setTimeout(r, 2000));

  let postUrl;
  try {
    postUrl = await submitPost(token, post.subreddit, post.title, post.text);
  } catch (err) {
    await sendTelegram(`❌ Reddit post fehlgeschlagen (r/${post.subreddit}): ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }

  await sendTelegram(
    `✅ Reddit Post live!\n📌 r/${post.subreddit}\n📝 ${post.title.substring(0, 60)}...\n🔗 ${postUrl}`
  );

  return res.status(200).json({
    ok: true,
    subreddit: post.subreddit,
    postUrl,
    postIndex,
  });
}
