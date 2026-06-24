// Instagram Auto-Poster für @aaiitecc (17841478315197796)
// Verbunden mit FB Page: AiiteC (1016738738178786)
// Cron: Di/Do/Sa 11:00 UTC
// Benötigt: FB_PAGE_ACCESS_TOKEN mit instagram_content_publish + pages_manage_posts

const IG_USER_ID = process.env.IG_USER_ID || '17841478315197796';
const FB_TOKEN = process.env.FB_PAGE_ACCESS_TOKEN;
const FB_PAGE_ID = process.env.FB_PAGE_ID || '1016738738178786';
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';

// Branded promotional images (1080x1080) — austauschbar wenn eigene Bilder vorhanden
const IMAGE_URLS = [
  'https://picsum.photos/seed/aiitec-ki1/1080/1080',
  'https://picsum.photos/seed/aiitec-income2/1080/1080',
  'https://picsum.photos/seed/aiitec-auto3/1080/1080',
  'https://picsum.photos/seed/aiitec-blog4/1080/1080',
  'https://picsum.photos/seed/aiitec-aff5/1080/1080',
  'https://picsum.photos/seed/aiitec-bot6/1080/1080',
];

// Deutsche Instagram-Post Vorlagen — rotierend
const POSTS = [
  {
    caption: `🤖 KI-Einkommen 2026 — meine ehrliche Bilanz nach 4 Monaten

€111 passiv verdient. Vollautomatisch. Keine Ads.

Was ich aufgebaut habe:
✅ LinkedIn postet Mo/Mi/Fr automatisch
✅ E-Mail-Sequenz läuft täglich
✅ Digistore24 verkauft auch nachts
✅ Telegram meldet jeden Verkauf sofort

Der deutsche Markt ist 5x weniger gesättigt als Englisch. Das ist der Vorteil.

90-Day Blueprint auf Deutsch 👆 Link in Bio

#KI #PassivesEinkommen #OnlineBusiness #Automatisierung #Deutschland #GeldVerdienen #KITools #DigitalesProdukt`,
    imageIdx: 0,
  },
  {
    caption: `💡 Warum 2026 der beste Zeitpunkt für KI-Business ist

2023: "KI ist interessant"
2024: "Ich sollte was machen"
2025: Erste verdienen bereits
2026: ← DU BIST HIER

Wer jetzt startet, hat noch 18–24 Monate Vorsprung vor dem Mainstream.

Mein System für den deutschen Markt:
→ Digitales Produkt + Automation + E-Mail-Liste
→ Läuft 24/7 ohne mich
→ €37 einmalig, kein Abo

Details 👆 Link in Bio

#KIBusiness #Zeitpunkt #PassivesEinkommen #OnlineBusiness #Automation #GeldVerdienen2026`,
    imageIdx: 1,
  },
  {
    caption: `📊 Meine Zahlen (100% transparent):

Monat 1: €0 — Setup
Monat 2: €0 — Testing
Monat 3: €37 🎉 erster Verkauf
Monat 4: €74 — 2 weitere (automatisch!)
Total: €111 passiv

Was ich tun musste: NICHTS in Monat 3+4.
Das System arbeitet selbstständig.

Wie? Vollständiger Guide 👆 Link in Bio
(€37 einmalig, 60-Tage-Garantie)

#Transparenz #EchtesEinkommen #PassivesEinkommen #KI #DigitalesMarketing #OnlineBusiness`,
    imageIdx: 2,
  },
  {
    caption: `🔥 32 SEO-Artikel in einer Woche — so geht autonomes Content Marketing

Ich habe 32 deutschsprachige Blog-Artikel automatisiert veröffentlicht.

Wie?
→ Artikel in Datenbank speichern
→ Automatisch auf Website
→ IndexNow an Google gesendet
→ LinkedIn postet Extracts automatisch

Ergebnis: SEO-Traffic ohne manuelle Arbeit

Den kompletten Blog lesen → autoincome-ai.vercel.app/blog

Das System dahinter → Link in Bio (€37)

#SEO #ContentMarketing #Automatisierung #KI #Blogging #GeldVerdienen #OnlineBusiness`,
    imageIdx: 3,
  },
  {
    caption: `💰 50% Provision — verdiene bis zu €48,50 pro Vermittlung

Kein eigenes Produkt nötig.

Werde Affiliate für:
→ AI Income Machine Blueprint €37 → du verdienst €18,50 pro Sale
→ SuperMegaBot System €97 → du verdienst €48,50 pro Sale

Auszahlung: wöchentlich via Digistore24
Start: kostenlos, sofort

10 Vermittlungen/Monat = €185–485 passiv

Alle Details + Anmeldung 👆 Link in Bio

#AffiliateMarketing #Digistore24 #PassivesEinkommen #Provision #OnlineBusiness #GeldVerdienen`,
    imageIdx: 4,
  },
  {
    caption: `🚀 SuperMegaBot — das vollautomatische KI-System für €97

Was drin ist:
✅ LinkedIn Bot (Mo/Mi/Fr automatisch)
✅ E-Mail-Sequenzen (täglich automatisch)
✅ Reddit Poster (Di/Sa automatisch)
✅ Telegram Revenue Reports (täglich 07:00)
✅ Shopify + Digistore24 Integration
✅ 32 SEO-Blog-Artikel inklusive
✅ 1-Click Deploy auf Railway

Für wen: Online-Unternehmer, Affiliates, digitale Nomaden

Früh-Käufer Preis: €97 (steigt noch)

Details + Kauf 👆 Link in Bio

#SuperMegaBot #Automatisierung #KI #OnlineBusiness #DigitalNomad #PassivesEinkommen`,
    imageIdx: 5,
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

async function refreshFBToken() {
  // Exchange short-lived for long-lived token (60 days)
  const FB_APP_ID = process.env.FB_APP_ID || '1225412136200609';
  const FB_APP_SECRET = process.env.FB_APP_SECRET || '9a93a2ea6c19069baf5e61ce29ce7c1a';
  const r = await fetch(
    `https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${FB_APP_ID}&client_secret=${FB_APP_SECRET}&fb_exchange_token=${FB_TOKEN}`
  );
  const data = await r.json();
  return data.access_token || FB_TOKEN;
}

async function getPageToken(userToken) {
  // Get Page Access Token for the specific page
  const r = await fetch(
    `https://graph.facebook.com/v21.0/${FB_PAGE_ID}?fields=access_token&access_token=${userToken}`
  );
  const data = await r.json();
  return data.access_token || userToken;
}

async function postToInstagram(pageToken, imageUrl, caption) {
  // Step 1: Create media container
  const containerResp = await fetch(`https://graph.facebook.com/v21.0/${IG_USER_ID}/media`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image_url: imageUrl,
      caption: caption,
      access_token: pageToken,
    }),
  });
  const container = await containerResp.json();
  if (!container.id) throw new Error(`Container failed: ${JSON.stringify(container).substring(0, 300)}`);

  // Wait 3 seconds for media processing
  await new Promise((r) => setTimeout(r, 3000));

  // Step 2: Publish
  const publishResp = await fetch(`https://graph.facebook.com/v21.0/${IG_USER_ID}/media_publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      creation_id: container.id,
      access_token: pageToken,
    }),
  });
  const published = await publishResp.json();
  if (!published.id) throw new Error(`Publish failed: ${JSON.stringify(published).substring(0, 300)}`);
  return published.id;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  if (!FB_TOKEN) {
    const msg = `❌ Instagram Poster: FB_PAGE_ACCESS_TOKEN fehlt!\n\n` +
      `Token holen:\n` +
      `1. Öffne: developers.facebook.com/tools/explorer\n` +
      `2. App: 1225412136200609 (automatic)\n` +
      `3. Permissions: pages_manage_posts + instagram_content_publish\n` +
      `4. Generate Token → in Vercel als FB_PAGE_ACCESS_TOKEN setzen`;
    await sendTelegram(msg);
    return res.status(500).json({ error: 'FB_PAGE_ACCESS_TOKEN not set', fix: msg });
  }

  // Select post by week + day slot
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay(); // 2=Tue, 4=Thu, 6=Sat
  const daySlot = dayOfWeek === 2 ? 0 : dayOfWeek === 4 ? 1 : 2;
  const postIdx = (weekNum * 3 + daySlot) % POSTS.length;
  const post = POSTS[postIdx];
  const imageUrl = IMAGE_URLS[post.imageIdx];

  let pageToken;
  try {
    const longToken = await refreshFBToken();
    pageToken = await getPageToken(longToken);
  } catch (err) {
    await sendTelegram(`❌ Instagram Token Fehler: ${err.message}`);
    return res.status(500).json({ error: err.message });
  }

  let mediaId;
  try {
    mediaId = await postToInstagram(pageToken, imageUrl, post.caption);
  } catch (err) {
    await sendTelegram(`❌ Instagram Post fehlgeschlagen: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ error: err.message });
  }

  await sendTelegram(
    `✅ Instagram @aaiitecc Post live!\n` +
    `📸 Media ID: ${mediaId}\n` +
    `📝 ${post.caption.substring(0, 80)}...\n` +
    `🔗 instagram.com/aaiitecc`
  );

  return res.status(200).json({ ok: true, mediaId, postIdx });
}
