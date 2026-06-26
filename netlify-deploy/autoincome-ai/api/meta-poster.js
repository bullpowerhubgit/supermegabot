// Meta Auto-Poster: Instagram @aaiitecc + Facebook AiiteC Page + Threads
// Instagram: Di/Do/Sa 11:00 UTC | Facebook: Mo/Mi/Fr 12:00 UTC | Threads: täglich
// Benötigt: FB_PAGE_ACCESS_TOKEN, THREADS_ACCESS_TOKEN

const IG_USER_ID = process.env.IG_USER_ID || '17841478315197796';
const FB_PAGE_ID = process.env.FB_PAGE_ID || '1016738738178786';
const FB_APP_ID = process.env.FB_APP_ID || '1225412136200609';
const FB_APP_SECRET = process.env.FB_APP_SECRET;
const THREADS_APP_ID = process.env.THREADS_APP_ID || '1224559653149864';
const THREADS_APP_SECRET = process.env.THREADS_APP_SECRET;
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_ANON_KEY;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';

const FB_REDIRECT_URI = 'https://autoincome-ai.vercel.app/api/meta-poster?action=fb-auth';
const THREADS_REDIRECT_URI = 'https://autoincome-ai.vercel.app/api/meta-poster?action=threads-auth';

const IMAGE_SEEDS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120];
function getPicsumUrl(seed, width = 1080, height = 1080) {
  return `https://picsum.photos/seed/${seed}/${width}/${height}`;
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

const THREADS_POSTS = [
  `🤖 KI-Einkommen 2026: €111 in 4 Monaten — vollautomatisch, ohne Ads, ohne Kunden-Calls.\n\nMein System postet, verkauft und meldet mir alles via Telegram.\n\nDer 90-Day Blueprint: ${PRODUCT_URL}`,
  `💡 2026 ist das beste Jahr für KI-Automation im deutschsprachigen Markt.\n\n85% weniger Konkurrenz als Englisch. Gleiche Kaufkraft.\n\nKompletter Guide (kostenlos): ${BLOG_URL}`,
  `📊 Meine echten Zahlen — keine Verkäufer-Phantasien:\n\nMonat 1–2: €0 (Aufbau)\nMonat 3: €37 ✅ erster Verkauf\nMonat 4: €74 ✅ zwei weitere automatisch\n\nSystem läuft ohne mich. Blueprint: ${PRODUCT_URL}`,
  `💰 50% Provision — €18,50 bis €48,50 pro Empfehlung.\n\nKein Eigenkapital. Kein Risiko. Wöchentliche Auszahlung via Digistore24.\n\nAffiliates werden (kostenlos): ${AFFILIATE_URL}`,
  `🚀 SuperMegaBot für €97: LinkedIn + Instagram + Reddit + E-Mail — alles automatisch.\n\nFrüh-Käufer Preis nur noch bis 30.06.2026: ${UPSELL_URL}`,
  `📝 32+ kostenlose deutschsprachige Guides:\n• Passives Einkommen 2026\n• KI Business starten ohne Kapital\n• Digistore24 Produkt erstellen\n• Affiliate Marketing für Anfänger\n\n${BLOG_URL}`,
  `🔥 Nur noch wenige Tage bis der Junipreis endet.\n\nAI Income Machine: €37 → danach €97\nSuperMegaBot: €97 → danach €297\n\nJetzt sichern: ${PRODUCT_URL}`,
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

async function saveToken(platform, access_token, user_id = null) {
  if (!SUPABASE_URL || !SUPABASE_KEY) return false;
  const r = await fetch(`${SUPABASE_URL}/rest/v1/oauth_tokens`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${SUPABASE_KEY}`,
      'apikey': SUPABASE_KEY,
      'Content-Type': 'application/json',
      'Prefer': 'resolution=merge-duplicates,return=minimal',
    },
    body: JSON.stringify({ platform, access_token, user_id, updated_at: new Date().toISOString() }),
  });
  return r.ok;
}

async function getToken(platform) {
  if (!SUPABASE_URL || !SUPABASE_KEY) return null;
  const r = await fetch(`${SUPABASE_URL}/rest/v1/oauth_tokens?platform=eq.${platform}&select=access_token,user_id`, {
    headers: { 'Authorization': `Bearer ${SUPABASE_KEY}`, 'apikey': SUPABASE_KEY },
  });
  const data = await r.json();
  return data?.[0] || null;
}

async function getLongLivedToken(token) {
  if (!FB_APP_SECRET || !token) return token;
  const r = await fetch(
    `https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${FB_APP_ID}&client_secret=${FB_APP_SECRET}&fb_exchange_token=${token}`
  );
  const data = await r.json();
  return data.access_token || token;
}

async function getPageToken(userToken) {
  const r = await fetch(
    `https://graph.facebook.com/v21.0/${FB_PAGE_ID}?fields=access_token&access_token=${userToken}`
  );
  const data = await r.json();
  return data.access_token || userToken;
}

async function resolveImageUrl(keyword) {
  const idx = IMAGE_SEEDS[Math.abs(keyword.charCodeAt(0) + keyword.length) % IMAGE_SEEDS.length];
  return getPicsumUrl(idx, 1080, 1080);
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

async function postToThreads(text, token, userId) {
  if (!token) throw new Error('Threads token not set');
  const containerResp = await fetch(`https://graph.threads.net/v1.0/${userId}/threads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, media_type: 'TEXT', access_token: token }),
  });
  const container = await containerResp.json();
  if (!container.id) throw new Error(`Threads container: ${JSON.stringify(container).substring(0, 200)}`);
  await new Promise((r) => setTimeout(r, 3000));
  const publishResp = await fetch(`https://graph.threads.net/v1.0/${userId}/threads_publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ creation_id: container.id, access_token: token }),
  });
  const published = await publishResp.json();
  if (!published.id) throw new Error(`Threads publish: ${JSON.stringify(published).substring(0, 200)}`);
  return published.id;
}

export default async function handler(req, res) {
  const { action, code, error } = req.query || {};

  // Threads OAuth
  if (action === 'threads-auth') {
    const SCOPES = 'threads_basic,threads_content_publish';
    if (error) {
      await sendTelegram(`❌ Threads OAuth abgelehnt: ${error}`);
      return res.status(200).send(`<html><body><h2>❌ Abgebrochen</h2><p>${error}</p></body></html>`);
    }
    if (!code) {
      const url = `https://threads.net/oauth/authorize?client_id=${THREADS_APP_ID}&redirect_uri=${encodeURIComponent(THREADS_REDIRECT_URI)}&scope=${encodeURIComponent(SCOPES)}&response_type=code`;
      return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h2>🧵 Threads OAuth</h2><p>Verbinde deinen Threads Account (AiiteC @aaiitecc)</p><a href="${url}" style="display:inline-block;background:#000;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700">Mit Threads autorisieren →</a><p style="color:#64748b;font-size:0.85rem;margin-top:20px">Scopes: ${SCOPES}</p><p style="color:#64748b;font-size:0.8rem">Redirect: ${THREADS_REDIRECT_URI}</p></body></html>`);
    }
    try {
      const tkRes = await fetch('https://graph.threads.net/oauth/access_token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: THREADS_APP_ID,
          client_secret: THREADS_APP_SECRET || '',
          grant_type: 'authorization_code',
          redirect_uri: THREADS_REDIRECT_URI,
          code,
        }),
      });
      const tkData = await tkRes.json();
      if (tkData.error) throw new Error(String(tkData.error_message || tkData.error));
      const shortToken = tkData.access_token;
      const userId = tkData.user_id;
      const longRes = await fetch(
        `https://graph.threads.net/access_token?grant_type=th_exchange_token&client_id=${THREADS_APP_ID}&client_secret=${THREADS_APP_SECRET}&access_token=${shortToken}`
      );
      const longData = await longRes.json();
      const longToken = longData.access_token || shortToken;
      await saveToken('threads', longToken, userId ? String(userId) : null);
      await sendTelegram(`✅ <b>Threads Token gespeichert!</b>\nUser ID: ${userId}\nThreads Poster läuft jetzt täglich!`);
      return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h2>✅ Threads verbunden!</h2><p>Token in Supabase gespeichert. Threads-Poster läuft täglich!</p><p style="color:#059669">Nächster Post: morgen 11:00 UTC</p></body></html>`);
    } catch (err) {
      await sendTelegram(`❌ Threads OAuth Fehler: ${err.message.substring(0, 200)}`);
      return res.status(200).send(`<html><body><h2>❌ Fehler</h2><pre>${err.message}</pre></body></html>`);
    }
  }

  // Facebook OAuth (action=fb-auth)
  if (action === 'fb-auth') {
    const SCOPES = 'pages_manage_posts,instagram_content_publish,pages_read_engagement,pages_show_list,instagram_basic';
    if (error) {
      await sendTelegram(`❌ FB OAuth abgelehnt: ${error}`);
      return res.status(200).send(`<html><body><h2>❌ Abgebrochen</h2><p>${error}</p></body></html>`);
    }
    if (!code) {
      const url = `https://www.facebook.com/v21.0/dialog/oauth?client_id=${FB_APP_ID}&redirect_uri=${encodeURIComponent(FB_REDIRECT_URI)}&scope=${encodeURIComponent(SCOPES)}&response_type=code`;
      return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h2>🔐 Facebook OAuth</h2><a href="${url}" style="display:inline-block;background:#1877f2;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700">Mit Facebook autorisieren →</a><p style="color:#64748b;font-size:0.85rem;margin-top:20px">Scopes: ${SCOPES}</p></body></html>`);
    }
    try {
      const tkRes = await fetch(`https://graph.facebook.com/v21.0/oauth/access_token?client_id=${FB_APP_ID}&redirect_uri=${encodeURIComponent(FB_REDIRECT_URI)}&client_secret=${FB_APP_SECRET}&code=${code}`);
      const tkData = await tkRes.json();
      if (tkData.error) throw new Error(JSON.stringify(tkData.error));
      const longRes = await fetch(`https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${FB_APP_ID}&client_secret=${FB_APP_SECRET}&fb_exchange_token=${tkData.access_token}`);
      const longData = await longRes.json();
      const longToken = longData.access_token || tkData.access_token;
      const pagesRes = await fetch(`https://graph.facebook.com/v21.0/me/accounts?access_token=${longToken}`);
      const pagesData = await pagesRes.json();
      const page = pagesData.data?.find(p => p.id === FB_PAGE_ID) || pagesData.data?.[0];
      if (!page) throw new Error(`Seite ${FB_PAGE_ID} nicht gefunden: ${JSON.stringify(pagesData.data?.map(p => p.id))}`);
      await saveToken('facebook', page.access_token, FB_PAGE_ID);
      await sendTelegram(`✅ <b>FB Token gespeichert!</b>\nSeite: ${page.name} (${FB_PAGE_ID})\nToken: ${page.access_token.substring(0, 20)}...\nMeta-Poster läuft wieder!`);
      return res.status(200).send(`<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h2>✅ Token gespeichert!</h2><p>Seite: <strong>${page.name}</strong></p><p style="color:#059669">Meta-Poster läuft wieder! Token in Supabase gesichert.</p></body></html>`);
    } catch (err) {
      await sendTelegram(`❌ FB OAuth Fehler: ${err.message.substring(0, 200)}`);
      return res.status(200).send(`<html><body><h2>❌ Fehler</h2><pre>${err.message}</pre></body></html>`);
    }
  }

  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  // Fetch live tokens from Supabase (fallback to ENV)
  const fbRow = await getToken('facebook');
  const FB_TOKEN = fbRow?.access_token || process.env.FB_PAGE_ACCESS_TOKEN || null;
  const threadsRow = await getToken('threads');
  const THREADS_TOKEN = threadsRow?.access_token || process.env.THREADS_ACCESS_TOKEN || null;
  const THREADS_USER_ID_LIVE = threadsRow?.user_id || process.env.THREADS_USER_ID || '17841478315197796';

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay(); // 0=So,1=Mo,2=Di,3=Mi,4=Do,5=Fr,6=Sa
  const dayOfYear = Math.floor((Date.now() - new Date(now.getFullYear(), 0, 0)) / 86400000);
  const results = [];

  // Instagram: Di=2, Do=4, Sa=6
  if ([2, 4, 6].includes(dayOfWeek)) {
    if (!FB_TOKEN) {
      results.push({ platform: 'instagram', error: 'FB token not set — visit /api/meta-poster?action=fb-auth' });
    } else {
      try {
        const longToken = await getLongLivedToken(FB_TOKEN);
        const pageToken = await getPageToken(longToken);
        const daySlot = dayOfWeek === 2 ? 0 : dayOfWeek === 4 ? 1 : 2;
        const idx = (weekNum * 3 + daySlot) % IG_POSTS.length;
        const post = IG_POSTS[idx];
        const imageUrl = await resolveImageUrl(post.keyword);
        const mediaId = await postInstagram(pageToken, imageUrl, post.caption);
        await sendTelegram(`✅ Instagram @aaiitecc post live!\n📸 Media ID: ${mediaId}\n📝 ${post.caption.substring(0, 60)}...`);
        results.push({ platform: 'instagram', mediaId, idx });
      } catch (err) {
        await sendTelegram(`❌ Instagram fehlgeschlagen: ${err.message.substring(0, 150)}`);
        results.push({ platform: 'instagram', error: err.message });
      }
    }
  }

  // Facebook: Mo=1, Mi=3, Fr=5
  if ([1, 3, 5].includes(dayOfWeek)) {
    if (!FB_TOKEN) {
      results.push({ platform: 'facebook', error: 'FB token not set — visit /api/meta-poster?action=fb-auth' });
    } else {
      try {
        const longToken = await getLongLivedToken(FB_TOKEN);
        const pageToken = await getPageToken(longToken);
        const daySlot = dayOfWeek === 1 ? 0 : dayOfWeek === 3 ? 1 : 2;
        const idx = (weekNum * 3 + daySlot) % FB_POSTS.length;
        const post = FB_POSTS[idx];
        const postId = await postFacebook(pageToken, post.message, post.link);
        await sendTelegram(`✅ Facebook AiiteC Page post live!\n📌 Post ID: ${postId}\n📝 ${post.message.substring(0, 60)}...`);
        results.push({ platform: 'facebook', postId, idx });
      } catch (err) {
        await sendTelegram(`❌ Facebook fehlgeschlagen: ${err.message.substring(0, 150)}`);
        results.push({ platform: 'facebook', error: err.message });
      }
    }
  }

  // Threads: täglich (wenn Token vorhanden)
  if (THREADS_TOKEN) {
    try {
      const idx = dayOfYear % THREADS_POSTS.length;
      const postId = await postToThreads(THREADS_POSTS[idx], THREADS_TOKEN, THREADS_USER_ID_LIVE);
      await sendTelegram(`✅ Threads @aaiitecc post live!\n📌 Post ID: ${postId}\n📝 ${THREADS_POSTS[idx].substring(0, 60)}...`);
      results.push({ platform: 'threads', postId, idx });
    } catch (err) {
      await sendTelegram(`❌ Threads fehlgeschlagen: ${err.message.substring(0, 150)}`);
      results.push({ platform: 'threads', error: err.message });
    }
  } else {
    results.push({ platform: 'threads', skipped: true, reason: 'THREADS_ACCESS_TOKEN not set — visit /api/meta-poster?action=threads-auth' });
  }

  return res.status(200).json({ ok: true, results, day: dayOfWeek });
}
