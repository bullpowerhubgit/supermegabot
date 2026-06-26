// Facebook/Instagram OAuth Callback + Token Manager
// GET /api/fb-callback?code=... → exchange code for long-lived page token → store in Vercel
// GET /api/fb-callback?action=url → return the OAuth URL to start the flow
// Stores: FB_PAGE_ACCESS_TOKEN in Vercel env vars + sends to Telegram

const FB_APP_ID = process.env.FB_APP_ID || '1225412136200609';
const FB_APP_SECRET = process.env.FB_APP_SECRET || '9a93a2ea6c19069baf5e61ce29ce7c1a';
const FB_PAGE_ID = process.env.FB_PAGE_ID || '1016738738178786';
const VERCEL_TOKEN = process.env.VERCEL_API_TOKEN;
const VERCEL_PROJECT_ID = process.env.VERCEL_PROJECT_ID || 'prj_dOdBHrPrCns5V1H3rSNi2dmyec6H';
const VERCEL_TEAM_ID = process.env.VERCEL_TEAM_ID || 'team_xulvdt7sib2RSt4BNoqVWeSy';
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const REDIRECT_URI = 'https://autoincome-ai.vercel.app/api/fb-callback';

const SCOPES = [
  'pages_manage_posts',
  'instagram_content_publish',
  'pages_read_engagement',
  'pages_show_list',
  'instagram_basic',
  'business_management',
].join(',');

async function sendTelegram(msg) {
  if (!TELEGRAM_BOT || !TELEGRAM_CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML' }),
    });
  } catch {}
}

async function setVercelEnv(key, value) {
  if (!VERCEL_TOKEN) return false;
  // Check if env var exists first
  const listRes = await fetch(
    `https://api.vercel.com/v9/projects/${VERCEL_PROJECT_ID}/env?teamId=${VERCEL_TEAM_ID}`,
    { headers: { Authorization: `Bearer ${VERCEL_TOKEN}` } }
  );
  const list = await listRes.json();
  const existing = list.envs?.find(e => e.key === key && e.target?.includes('production'));

  if (existing) {
    // Update existing
    const r = await fetch(
      `https://api.vercel.com/v9/projects/${VERCEL_PROJECT_ID}/env/${existing.id}?teamId=${VERCEL_TEAM_ID}`,
      {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${VERCEL_TOKEN}`, 'content-type': 'application/json' },
        body: JSON.stringify({ value }),
      }
    );
    return r.ok;
  } else {
    // Create new
    const r = await fetch(
      `https://api.vercel.com/v10/projects/${VERCEL_PROJECT_ID}/env?teamId=${VERCEL_TEAM_ID}`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${VERCEL_TOKEN}`, 'content-type': 'application/json' },
        body: JSON.stringify({ key, value, type: 'encrypted', target: ['production'] }),
      }
    );
    return r.ok;
  }
}

export default async function handler(req, res) {
  const { code, action, error } = req.query || {};

  if (error) {
    await sendTelegram(`❌ FB OAuth abgelehnt: ${error}`);
    return res.status(200).send(`<html><body><h2>❌ Abgebrochen</h2><p>${error}</p></body></html>`);
  }

  // Return OAuth URL
  if (action === 'url') {
    const url = `https://www.facebook.com/v21.0/dialog/oauth?client_id=${FB_APP_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=${encodeURIComponent(SCOPES)}&response_type=code`;
    return res.status(200).json({ url, redirect_uri: REDIRECT_URI });
  }

  if (!code) {
    const url = `https://www.facebook.com/v21.0/dialog/oauth?client_id=${FB_APP_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=${encodeURIComponent(SCOPES)}&response_type=code`;
    return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px">
      <h2>🔐 Facebook OAuth</h2>
      <p>Klicke hier um Facebook/Instagram zu autorisieren:</p>
      <a href="${url}" style="display:inline-block;background:#1877f2;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700">Mit Facebook autorisieren →</a>
      <p style="color:#64748b;font-size:0.85rem;margin-top:20px">Scopes: ${SCOPES}</p>
    </body></html>`);
  }

  // Exchange code for short-lived user token
  const tokenRes = await fetch(
    `https://graph.facebook.com/v21.0/oauth/access_token?client_id=${FB_APP_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&client_secret=${FB_APP_SECRET}&code=${code}`
  );
  const tokenData = await tokenRes.json();

  if (tokenData.error) {
    await sendTelegram(`❌ FB Token-Exchange Fehler: ${JSON.stringify(tokenData.error)}`);
    return res.status(200).send(`<html><body><h2>❌ Fehler</h2><pre>${JSON.stringify(tokenData, null, 2)}</pre></body></html>`);
  }

  const shortToken = tokenData.access_token;

  // Exchange for long-lived token (60 days)
  const longRes = await fetch(
    `https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${FB_APP_ID}&client_secret=${FB_APP_SECRET}&fb_exchange_token=${shortToken}`
  );
  const longData = await longRes.json();
  const longToken = longData.access_token || shortToken;

  // Get page access token for AiiteC page
  const pagesRes = await fetch(
    `https://graph.facebook.com/v21.0/me/accounts?access_token=${longToken}`
  );
  const pagesData = await pagesRes.json();
  const page = pagesData.data?.find(p => p.id === FB_PAGE_ID) || pagesData.data?.[0];

  if (!page) {
    await sendTelegram(`❌ Seite ${FB_PAGE_ID} nicht gefunden!\nVerfügbare Seiten: ${JSON.stringify(pagesData.data?.map(p => p.id + ': ' + p.name))}`);
    return res.status(200).send(`<html><body><h2>⚠️ Seite nicht gefunden</h2><pre>${JSON.stringify(pagesData, null, 2)}</pre></body></html>`);
  }

  const pageToken = page.access_token;
  const pageName = page.name;

  // Store tokens in Vercel env vars
  const results = [];
  results.push(await setVercelEnv('FB_PAGE_ACCESS_TOKEN', pageToken));
  results.push(await setVercelEnv('FB_USER_LONG_TOKEN', longToken));

  await sendTelegram(`✅ <b>Facebook Token erneuert!</b>
📄 Seite: ${pageName} (${FB_PAGE_ID})
🔑 Page Token: ${pageToken.substring(0, 20)}...
📦 In Vercel gespeichert: ${results.filter(Boolean).length}/2
⚡ Meta-Poster läuft wieder!`);

  return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px">
    <h2>✅ Facebook Token gespeichert!</h2>
    <p><strong>Seite:</strong> ${pageName} (${FB_PAGE_ID})</p>
    <p><strong>Token:</strong> ${pageToken.substring(0, 20)}...</p>
    <p style="color:#059669">Token wurde in Vercel Env-Vars gespeichert. Meta-Poster läuft wieder!</p>
    <p><a href="https://autoincome-ai.vercel.app">Zurück zur Website</a></p>
  </body></html>`);
}
