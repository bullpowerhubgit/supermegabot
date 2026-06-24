// Facebook Page Auto-Poster — AiiteC Page (1016738738178786)
// Cron: Mo/Mi/Fr 12:00 UTC (nach LinkedIn um 09:00)
// Benötigt: FB_PAGE_ACCESS_TOKEN mit pages_manage_posts

const FB_PAGE_ID = process.env.FB_PAGE_ID || '1016738738178786';
const FB_TOKEN = process.env.FB_PAGE_ACCESS_TOKEN;
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';

const POSTS = [
  {
    message: `🤖 Automatisch Geld verdienen mit KI — so geht's 2026

Nach 4 Monaten: €111 passiv. Vollautomatisch. Keine Werbung.

Das System:
✅ LinkedIn postet Mo/Mi/Fr von selbst
✅ E-Mails werden täglich verschickt
✅ Digistore24 verkauft rund um die Uhr
✅ Telegram meldet jeden Verkauf

Der komplette 90-Day Blueprint auf Deutsch: ${PRODUCT_URL}

#KI #PassivesEinkommen #OnlineBusiness #Deutschland`,
    link: PRODUCT_URL,
  },
  {
    message: `💡 Der deutschsprachige KI-Markt 2026 — riesige Chance

85% weniger Konkurrenz als auf Englisch.
Trotzdem: Gleiche Kaufkraft, gleicher Markt.

Was ich aufbaue:
→ Automatisches Blogsystem (32 Artikel)
→ LinkedIn-Automation (3x/Woche)
→ E-Mail-Sequenzen (täglich)

Ergebnis: €111 in 4 Monaten ohne manuelle Verkaufsarbeit.

Wie du das nachmachst: ${BLOG_URL}

#KI #GeldVerdienen #OnlineMarketing #Automatisierung`,
    link: BLOG_URL,
  },
  {
    message: `📊 Transparenz: So verdiene ich passiv mit KI

Monat 1–2: €0 (Aufbau)
Monat 3: €37 (1. Verkauf!)
Monat 4: €74 (2 weitere — automatisch)

Was sich verändert hat: NICHTS. Das System läuft. Ich check nur Telegram.

Kompletter Blueprint: ${PRODUCT_URL} (€37, 60-Tage-Garantie)

#EchtesEinkommen #Transparenz #KI #PassivesEinkommen`,
    link: PRODUCT_URL,
  },
  {
    message: `🔥 Neues Produkt: SuperMegaBot KI-Automation System für €97

Das vollständige KI-Automation System:
• LinkedIn + Reddit + Instagram Bots
• E-Mail-Automation (täglich)
• Shopify + Digistore24 Integration
• Telegram Revenue Reports
• 32 SEO-Artikel inklusive
• 1-Click Deploy auf Railway

Für: Online-Unternehmer die alles automatisieren wollen.

Früh-Käufer Preis: ${UPSELL_URL}

#SuperMegaBot #KIAutomation #OnlineBusiness #Neuheit`,
    link: UPSELL_URL,
  },
  {
    message: `💰 50% Affiliate-Provision — verdiene bis zu €48,50 pro Sale

Unser Affiliate-Programm:
→ AI Income Machine €37 → du verdienst €18,50
→ SuperMegaBot €97 → du verdienst €48,50

Auszahlung: wöchentlich automatisch via Digistore24
Kein Eigenkapital nötig, kein Risiko

Alle Infos: https://autoincome-ai.vercel.app/affiliate.html

#AffiliateMarketing #PassivesEinkommen #Provision #Digistore24`,
    link: 'https://autoincome-ai.vercel.app/affiliate.html',
  },
  {
    message: `📝 32 kostenlose KI-Einkommens-Guides auf Deutsch

Neue Artikel im Blog:
• Geld verdienen von Zuhause 2026
• Digistore24 Verkäufer werden
• KI Business Ideen 2026
• Passives Einkommen ohne Kapital
• Finanziell unabhängig werden
• Und 27 weitere...

Kostenlos lesen: ${BLOG_URL}

#KI #Blog #Ratgeber #GeldVerdienen #OnlineBusiness #Kostenlos`,
    link: BLOG_URL,
  },
];

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

async function getPageToken() {
  // Exchange user token for page token
  const r = await fetch(
    `https://graph.facebook.com/v21.0/${FB_PAGE_ID}?fields=access_token&access_token=${FB_TOKEN}`
  );
  const data = await r.json();
  return data.access_token || FB_TOKEN;
}

async function postToFacebook(pageToken, message, link) {
  const body = { message, access_token: pageToken };
  if (link) body.link = link;
  const r = await fetch(`https://graph.facebook.com/v21.0/${FB_PAGE_ID}/feed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok || data.error) throw new Error(JSON.stringify(data).substring(0, 300));
  return data.id;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  if (!FB_TOKEN) {
    await sendTelegram(
      '❌ Facebook Poster: FB_PAGE_ACCESS_TOKEN fehlt!\n' +
      'Token holen: developers.facebook.com/tools/explorer\n' +
      'App: 1225412136200609 | Permission: pages_manage_posts\n' +
      'Dann: vercel env add FB_PAGE_ACCESS_TOKEN production'
    );
    return res.status(500).json({ error: 'FB_PAGE_ACCESS_TOKEN not set' });
  }

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const daySlot = dayOfWeek === 1 ? 0 : dayOfWeek === 3 ? 1 : 2;
  const postIdx = (weekNum * 3 + daySlot) % POSTS.length;
  const post = POSTS[postIdx];

  let pageToken;
  try {
    pageToken = await getPageToken();
  } catch (err) {
    await sendTelegram(`❌ FB Token Fehler: ${err.message}`);
    return res.status(500).json({ error: err.message });
  }

  let postId;
  try {
    postId = await postToFacebook(pageToken, post.message, post.link);
  } catch (err) {
    await sendTelegram(`❌ Facebook Post fehlgeschlagen: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ error: err.message });
  }

  await sendTelegram(
    `✅ Facebook AiiteC Page Post live!\n📌 Post ID: ${postId}\n📝 ${post.message.substring(0, 80)}...`
  );
  return res.status(200).json({ ok: true, postId, postIdx });
}
