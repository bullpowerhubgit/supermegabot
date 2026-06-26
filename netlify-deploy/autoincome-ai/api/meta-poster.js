// Meta Auto-Poster: Instagram @aaiitecc + Facebook AiiteC Page
// Instagram: Di/Do/Sa 11:00 UTC | Facebook: Mo/Mi/Fr 12:00 UTC
// Benötigt: FB_PAGE_ACCESS_TOKEN (instagram_content_publish + pages_manage_posts)
// Bilder: Unsplash API (echte Fotos, kein Platzhalter)

const IG_USER_ID = process.env.IG_USER_ID || '17841478315197796';
const FB_PAGE_ID = process.env.FB_PAGE_ID || '1016738738178786';
const FB_APP_ID = process.env.FB_APP_ID || '1225412136200609';
const FB_APP_SECRET = process.env.FB_APP_SECRET;
const FB_TOKEN = process.env.FB_PAGE_ACCESS_TOKEN;
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';

// Echte Unsplash Bilder nach Keyword (kein API-Key nötig, stabile URLs)
const IMAGE_KEYWORDS = [
  'laptop,business,money',
  'entrepreneur,success,office',
  'automation,technology,ai',
  'passive,income,finance',
  'digital,marketing,growth',
  'online,business,startup',
];

function getUnsplashUrl(keyword, width = 1080, height = 1080) {
  return `https://source.unsplash.com/${width}x${height}/?${keyword}`;
}

const IG_POSTS = [
  {
    caption: `🤖 KI-Einkommen 2026 — meine ehrliche Bilanz nach 4 Monaten\n\n€111 passiv verdient. Vollautomatisch. Keine Ads.\n\nWas ich aufgebaut habe:\n✅ LinkedIn postet Mo/Mi/Fr automatisch\n✅ E-Mail-Sequenz läuft täglich\n✅ Digistore24 verkauft auch nachts\n✅ Telegram meldet jeden Verkauf sofort\n\nDer deutsche Markt ist 5x weniger gesättigt als Englisch. Das ist der Vorteil.\n\n90-Day Blueprint auf Deutsch 👆 Link in Bio\n\n#KI #PassivesEinkommen #OnlineBusiness #Automatisierung #Deutschland #GeldVerdienen`,
    keyword: 'laptop,business,money',
  },
  {
    caption: `💡 Warum 2026 der beste Zeitpunkt für KI-Business ist\n\n2023: "KI ist interessant"\n2024: "Ich sollte was machen"\n2025: Erste verdienen bereits\n2026: ← DU BIST HIER\n\nWer jetzt startet, hat noch 18–24 Monate Vorsprung.\n\nMein System für den deutschen Markt:\n→ Digitales Produkt + Automation + E-Mail-Liste\n→ Läuft 24/7 ohne mich\n→ €37 einmalig, kein Abo\n\nDetails 👆 Link in Bio\n\n#KIBusiness #PassivesEinkommen #OnlineBusiness #Automation #GeldVerdienen2026`,
    keyword: 'entrepreneur,success,office',
  },
  {
    caption: `📊 Meine Zahlen (100% transparent):\n\nMonat 1: €0 — Setup\nMonat 2: €0 — Testing\nMonat 3: €37 🎉 erster Verkauf\nMonat 4: €74 — 2 weitere automatisch!\nTotal: €111 passiv\n\nWas ich tun musste: NICHTS in Monat 3+4.\nDas System arbeitet selbstständig.\n\nWie? Vollständiger Guide 👆 Link in Bio\n(€37 einmalig, 60-Tage-Garantie)\n\n#Transparenz #EchtesEinkommen #PassivesEinkommen #KI #DigitalesMarketing`,
    keyword: 'automation,technology,ai',
  },
  {
    caption: `🔥 32 SEO-Artikel in einer Woche — autonomes Content Marketing\n\nIch habe 32 deutschsprachige Blog-Artikel automatisiert veröffentlicht.\n\nWie?\n→ Artikel in Datenbank speichern\n→ Automatisch auf Website\n→ IndexNow an Google gesendet\n→ LinkedIn postet Extracts automatisch\n\nErgebnis: SEO-Traffic ohne manuelle Arbeit\n\nDen kompletten Blog lesen → autoincome-ai.vercel.app/blog\n\nDas System dahinter → Link in Bio (€37)\n\n#SEO #ContentMarketing #Automatisierung #KI #GeldVerdienen`,
    keyword: 'digital,marketing,growth',
  },
  {
    caption: `💰 50% Provision — verdiene bis zu €48,50 pro Vermittlung\n\nKein eigenes Produkt nötig.\n\nWerde Affiliate für:\n→ AI Income Machine €37 → du verdienst €18,50 pro Sale\n→ SuperMegaBot €97 → du verdienst €48,50 pro Sale\n\nAuszahlung: wöchentlich via Digistore24\nStart: kostenlos, sofort\n\n10 Vermittlungen/Monat = €185–485 passiv\n\nAlle Details + Anmeldung 👆 Link in Bio\n\n#AffiliateMarketing #Digistore24 #PassivesEinkommen #Provision`,
    keyword: 'passive,income,finance',
  },
  {
    caption: `🚀 SuperMegaBot — das vollautomatische KI-System für €97\n\nWas drin ist:\n✅ LinkedIn Bot (Mo/Mi/Fr automatisch)\n✅ Instagram Bot (Di/Do/Sa automatisch)\n✅ E-Mail-Sequenzen (täglich automatisch)\n✅ Reddit Poster (Di/Sa automatisch)\n✅ Telegram Revenue Reports (täglich 07:00)\n✅ Shopify + Digistore24 Integration\n✅ 32 SEO-Blog-Artikel inklusive\n✅ 1-Click Deploy auf Railway\n\nFrüh-Käufer Preis: €97\n\nDetails + Kauf 👆 Link in Bio\n\n#SuperMegaBot #Automatisierung #KI #OnlineBusiness #PassivesEinkommen`,
    keyword: 'online,business,startup',
  },
];

const FB_POSTS = [
  {
    message: `🤖 Automatisch Geld verdienen mit KI — so geht's 2026\n\nNach 4 Monaten: €111 passiv. Vollautomatisch. Keine Werbung.\n\nDas System:\n✅ LinkedIn postet Mo/Mi/Fr von selbst\n✅ E-Mails werden täglich verschickt\n✅ Digistore24 verkauft rund um die Uhr\n✅ Telegram meldet jeden Verkauf\n\nDer komplette 90-Day Blueprint auf Deutsch: ${PRODUCT_URL}\n\n#KI #PassivesEinkommen #OnlineBusiness #Deutschland`,
    link: PRODUCT_URL,
  },
  {
    message: `💡 Der deutschsprachige KI-Markt 2026 — riesige Chance\n\n85% weniger Konkurrenz als auf Englisch.\nTrotzdem: Gleiche Kaufkraft, gleicher Markt.\n\nWas ich aufbaue:\n→ Automatisches Blogsystem (32 Artikel)\n→ LinkedIn-Automation (3x/Woche)\n→ E-Mail-Sequenzen (täglich)\n\nErgebnis: €111 in 4 Monaten ohne manuelle Verkaufsarbeit.\n\nWie du das nachmachst: ${BLOG_URL}\n\n#KI #GeldVerdienen #OnlineMarketing #Automatisierung`,
    link: BLOG_URL,
  },
  {
    message: `📊 Transparenz: So verdiene ich passiv mit KI\n\nMonat 1–2: €0 (Aufbau)\nMonat 3: €37 (1. Verkauf!)\nMonat 4: €74 (2 weitere — automatisch)\n\nWas sich verändert hat: NICHTS. Das System läuft. Ich check nur Telegram.\n\nKompletter Blueprint: ${PRODUCT_URL} (€37, 60-Tage-Garantie)\n\n#EchtesEinkommen #Transparenz #KI #PassivesEinkommen`,
    link: PRODUCT_URL,
  },
  {
    message: `🔥 Neues Produkt: SuperMegaBot KI-Automation System für €97\n\nDas vollständige KI-Automation System:\n• LinkedIn + Reddit + Instagram Bots\n• E-Mail-Automation (täglich)\n• Shopify + Digistore24 Integration\n• Telegram Revenue Reports\n• 32 SEO-Artikel inklusive\n• 1-Click Deploy auf Railway\n\nFrüh-Käufer Preis: €97\n\nDetails + Kauf: ${UPSELL_URL}\n\n#SuperMegaBot #KIAutomation #OnlineBusiness #Neuheit`,
    link: UPSELL_URL,
  },
  {
    message: `💰 50% Affiliate-Provision — verdiene bis zu €48,50 pro Sale\n\nUnser Affiliate-Programm:\n→ AI Income Machine €37 → du verdienst €18,50\n→ SuperMegaBot €97 → du verdienst €48,50\n\nAuszahlung: wöchentlich automatisch via Digistore24\nKein Eigenkapital nötig, kein Risiko\n\nAlle Infos: ${AFFILIATE_URL}\n\n#AffiliateMarketing #PassivesEinkommen #Provision #Digistore24`,
    link: AFFILIATE_URL,
  },
  {
    message: `📝 32 kostenlose KI-Einkommens-Guides auf Deutsch\n\nNeue Artikel im Blog:\n• Geld verdienen von Zuhause 2026\n• Digistore24 Verkäufer werden\n• KI Business Ideen 2026\n• Passives Einkommen ohne Kapital\n• Finanziell unabhängig werden\n• Und 27 weitere...\n\nKostenlos lesen: ${BLOG_URL}\n\n#KI #Blog #Ratgeber #GeldVerdienen #OnlineBusiness #Kostenlos`,
    link: BLOG_URL,
  },
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

async function getLongLivedToken() {
  if (!FB_APP_SECRET) return FB_TOKEN;
  const r = await fetch(
    `https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${FB_APP_ID}&client_secret=${FB_APP_SECRET}&fb_exchange_token=${FB_TOKEN}`
  );
  const data = await r.json();
  return data.access_token || FB_TOKEN;
}

async function getPageToken(userToken) {
  const r = await fetch(
    `https://graph.facebook.com/v21.0/${FB_PAGE_ID}?fields=access_token&access_token=${userToken}`
  );
  const data = await r.json();
  return data.access_token || userToken;
}

async function resolveImageUrl(keyword) {
  // Resolve Unsplash redirect to get stable direct image URL
  try {
    const unsplashUrl = getUnsplashUrl(keyword, 1080, 1080);
    const r = await fetch(unsplashUrl, { method: 'HEAD', redirect: 'follow' });
    if (r.url && r.url.includes('images.unsplash.com')) return r.url;
  } catch {}
  return getUnsplashUrl(keyword, 1080, 1080);
}

async function postInstagram(pageToken, imageUrl, caption) {
  const containerResp = await fetch(`https://graph.facebook.com/v21.0/${IG_USER_ID}/media`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_url: imageUrl, caption, access_token: pageToken }),
  });
  const container = await containerResp.json();
  if (!container.id) throw new Error(`IG container: ${JSON.stringify(container).substring(0, 200)}`);

  await new Promise((r) => setTimeout(r, 3000));

  const publishResp = await fetch(`https://graph.facebook.com/v21.0/${IG_USER_ID}/media_publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ creation_id: container.id, access_token: pageToken }),
  });
  const published = await publishResp.json();
  if (!published.id) throw new Error(`IG publish: ${JSON.stringify(published).substring(0, 200)}`);
  return published.id;
}

async function postFacebook(pageToken, message, link) {
  const body = { message, access_token: pageToken };
  if (link) body.link = link;
  const r = await fetch(`https://graph.facebook.com/v21.0/${FB_PAGE_ID}/feed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok || data.error) throw new Error(JSON.stringify(data).substring(0, 200));
  return data.id;
}

const VERCEL_TOKEN = process.env.VERCEL_API_TOKEN;
const VERCEL_PROJECT_ID = process.env.VERCEL_PROJECT_ID || 'prj_dOdBHrPrCns5V1H3rSNi2dmyec6H';
const VERCEL_TEAM_ID = process.env.VERCEL_TEAM_ID || 'team_xulvdt7sib2RSt4BNoqVWeSy';
const REDIRECT_URI = 'https://autoincome-ai.vercel.app/api/meta-poster?action=fb-auth';

async function setVercelEnv(key, value) {
  if (!VERCEL_TOKEN) return false;
  const listRes = await fetch(`https://api.vercel.com/v9/projects/${VERCEL_PROJECT_ID}/env?teamId=${VERCEL_TEAM_ID}`, { headers: { Authorization: `Bearer ${VERCEL_TOKEN}` } });
  const list = await listRes.json();
  const existing = list.envs?.find(e => e.key === key && e.target?.includes('production'));
  if (existing) {
    const r = await fetch(`https://api.vercel.com/v9/projects/${VERCEL_PROJECT_ID}/env/${existing.id}?teamId=${VERCEL_TEAM_ID}`, { method: 'PATCH', headers: { Authorization: `Bearer ${VERCEL_TOKEN}`, 'content-type': 'application/json' }, body: JSON.stringify({ value }) });
    return r.ok;
  }
  const r = await fetch(`https://api.vercel.com/v10/projects/${VERCEL_PROJECT_ID}/env?teamId=${VERCEL_TEAM_ID}`, { method: 'POST', headers: { Authorization: `Bearer ${VERCEL_TOKEN}`, 'content-type': 'application/json' }, body: JSON.stringify({ key, value, type: 'encrypted', target: ['production'] }) });
  return r.ok;
}

export default async function handler(req, res) {
  const { action, code, error } = req.query || {};

  // FB OAuth callback — no secret needed
  if (action === 'fb-auth' || code || error) {
    const SCOPES = 'pages_manage_posts,instagram_content_publish,pages_read_engagement,pages_show_list,instagram_basic';
    if (error) {
      await sendTelegram(`❌ FB OAuth abgelehnt: ${error}`);
      return res.status(200).send(`<html><body><h2>❌ Abgebrochen</h2><p>${error}</p></body></html>`);
    }
    if (!code) {
      const url = `https://www.facebook.com/v21.0/dialog/oauth?client_id=${FB_APP_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=${encodeURIComponent(SCOPES)}&response_type=code`;
      return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h2>🔐 Facebook OAuth</h2><a href="${url}" style="display:inline-block;background:#1877f2;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700">Mit Facebook autorisieren →</a><p style="color:#64748b;font-size:0.85rem;margin-top:20px">Scopes: ${SCOPES}</p></body></html>`);
    }
    try {
      const tkRes = await fetch(`https://graph.facebook.com/v21.0/oauth/access_token?client_id=${FB_APP_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&client_secret=${FB_APP_SECRET}&code=${code}`);
      const tkData = await tkRes.json();
      if (tkData.error) throw new Error(JSON.stringify(tkData.error));
      const longRes = await fetch(`https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${FB_APP_ID}&client_secret=${FB_APP_SECRET}&fb_exchange_token=${tkData.access_token}`);
      const longData = await longRes.json();
      const longToken = longData.access_token || tkData.access_token;
      const pagesRes = await fetch(`https://graph.facebook.com/v21.0/me/accounts?access_token=${longToken}`);
      const pagesData = await pagesRes.json();
      const page = pagesData.data?.find(p => p.id === FB_PAGE_ID) || pagesData.data?.[0];
      if (!page) throw new Error(`Seite ${FB_PAGE_ID} nicht gefunden: ${JSON.stringify(pagesData.data?.map(p => p.id))}`);
      await setVercelEnv('FB_PAGE_ACCESS_TOKEN', page.access_token);
      await sendTelegram(`✅ <b>FB Token gespeichert!</b>\nSeite: ${page.name} (${FB_PAGE_ID})\nToken: ${page.access_token.substring(0, 20)}...\nMeta-Poster läuft wieder!`);
      return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h2>✅ Token gespeichert!</h2><p>Seite: <strong>${page.name}</strong></p><p style="color:#059669">Meta-Poster läuft wieder! Nächster Post: morgen.</p></body></html>`);
    } catch (err) {
      await sendTelegram(`❌ FB OAuth Fehler: ${err.message.substring(0, 200)}`);
      return res.status(200).send(`<html><body><h2>❌ Fehler</h2><pre>${err.message}</pre></body></html>`);
    }
  }

  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  if (!FB_TOKEN) {
    await sendTelegram(
      '❌ Meta Poster: FB_PAGE_ACCESS_TOKEN fehlt!\n' +
      'Token holen: developers.facebook.com/tools/explorer\n' +
      'App: 1225412136200609\n' +
      'Permissions: pages_manage_posts + instagram_content_publish\n' +
      'vercel env add FB_PAGE_ACCESS_TOKEN production'
    );
    return res.status(500).json({ error: 'FB_PAGE_ACCESS_TOKEN not set' });
  }

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay(); // 0=So,1=Mo,2=Di,3=Mi,4=Do,5=Fr,6=Sa
  const results = [];

  let pageToken;
  try {
    const longToken = await getLongLivedToken();
    pageToken = await getPageToken(longToken);
  } catch (err) {
    await sendTelegram(`❌ Meta Token Fehler: ${err.message}`);
    return res.status(500).json({ error: err.message });
  }

  // Instagram: Di=2, Do=4, Sa=6
  if ([2, 4, 6].includes(dayOfWeek)) {
    const daySlot = dayOfWeek === 2 ? 0 : dayOfWeek === 4 ? 1 : 2;
    const idx = (weekNum * 3 + daySlot) % IG_POSTS.length;
    const post = IG_POSTS[idx];
    const imageUrl = await resolveImageUrl(post.keyword);
    try {
      const mediaId = await postInstagram(pageToken, imageUrl, post.caption);
      await sendTelegram(`✅ Instagram @aaiitecc post live!\n📸 Media ID: ${mediaId}\n📝 ${post.caption.substring(0, 60)}...`);
      results.push({ platform: 'instagram', mediaId, idx });
    } catch (err) {
      await sendTelegram(`❌ Instagram fehlgeschlagen: ${err.message.substring(0, 150)}`);
      results.push({ platform: 'instagram', error: err.message });
    }
  }

  // Facebook: Mo=1, Mi=3, Fr=5
  if ([1, 3, 5].includes(dayOfWeek)) {
    const daySlot = dayOfWeek === 1 ? 0 : dayOfWeek === 3 ? 1 : 2;
    const idx = (weekNum * 3 + daySlot) % FB_POSTS.length;
    const post = FB_POSTS[idx];
    try {
      const postId = await postFacebook(pageToken, post.message, post.link);
      await sendTelegram(`✅ Facebook AiiteC Page post live!\n📌 Post ID: ${postId}\n📝 ${post.message.substring(0, 60)}...`);
      results.push({ platform: 'facebook', postId, idx });
    } catch (err) {
      await sendTelegram(`❌ Facebook fehlgeschlagen: ${err.message.substring(0, 150)}`);
      results.push({ platform: 'facebook', error: err.message });
    }
  }

  return res.status(200).json({ ok: true, results, day: dayOfWeek });
}
