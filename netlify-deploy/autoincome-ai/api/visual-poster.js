// Visual Poster: TikTok + Pinterest + YouTube Community + Twitter/X
// TikTok: Mo/Mi/Fr 14:00 UTC | Pinterest: Mo/Do 13:00 UTC | YouTube: Mi/Sa 16:00 UTC | Twitter: Mo/Mi/Fr 15:00 UTC
// TikTok: Photo Post API oder Telegram-Skript
// Pinterest: Pins mit echten Unsplash-Bildern
// YouTube: Community Posts API oder Telegram-Fallback
// Twitter: OAuth 1.0a (@rudibot84)

import { createHmac } from 'crypto';

const TIKTOK_TOKEN = process.env.TIKTOK_ACCESS_TOKEN;
const PINTEREST_TOKEN = process.env.PINTEREST_ACCESS_TOKEN;
const PINTEREST_BOARD_ID = process.env.PINTEREST_BOARD_ID;
const YOUTUBE_TOKEN = process.env.YOUTUBE_OAUTH_TOKEN;
const TWITTER_API_KEY = process.env.TWITTER_API_KEY;
const TWITTER_API_SECRET = process.env.TWITTER_API_SECRET;
const TWITTER_ACCESS_TOKEN = process.env.TWITTER_ACCESS_TOKEN;
const TWITTER_ACCESS_SECRET = process.env.TWITTER_ACCESS_SECRET;
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';

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

// Twitter/X German tweet templates (280 chars max, Mo/Mi/Fr 15:00 UTC)
const TWEETS = [
  `🤖 €111 passiv verdient in 4 Monaten — vollautomatisch.

LinkedIn-Bot 3x/Woche, E-Mail-Sequenz, Digistore24-Produkt.
0 Stunden manuelle Arbeit danach.

Blueprint (Schritt-für-Schritt Plan) 👇
autoincome-ai.vercel.app

#PassivesEinkommen #KI #OnlineBusiness #Deutschland`,

  `🇩🇪 Der deutsche KI-Markt hat 85% weniger Konkurrenz als Englisch — bei gleicher Kaufkraft.

Wer jetzt startet, hat einen riesigen Zeitvorteil.

Mein System (gratis lesen): autoincome-ai.vercel.app/blog

#KIBusiness #DACH #Automation #GeldVerdienen`,

  `⚡ 2 Stunden Setup → danach 0 Stunden Arbeit.

1. Digistore24-Produkt (30 Min)
2. LinkedIn-Bot (30 Min)
3. Klaviyo E-Mail-Sequenz (1 Std)

Fertig. Alles läuft automatisch.

Blueprint: autoincome-ai.vercel.app

#KI #Automatisierung #PassivesEinkommen`,

  `💡 Affiliate-Programm: 50% Provision auf jeden Verkauf.

Blueprint €37 → du bekommst €18,50
SuperMegaBot €97 → du bekommst €48,50

Wöchentliche Auszahlung via Digistore24.
Keine Website nötig.

Kostenlos starten: autoincome-ai.vercel.app/affiliate.html

#Affiliate #PassivesEinkommen`,

  `📊 Woche 12 Update: Was funktioniert wirklich?

✅ LinkedIn: ~2.400 Impressionen/Post
✅ Klaviyo: 35% E-Mail-Öffnungsrate
✅ SEO-Blog: 52 Artikel, Google-Traffic steigt
❌ TikTok: Viel Aufwand, wenig Return

Mein System: autoincome-ai.vercel.app

#OnlineBusiness #KI #Transparenz`,

  `🚀 SuperMegaBot — das System das ich selbst benutze.

✅ LinkedIn Auto-Post 3x/Woche
✅ Instagram Di/Do/Sa automatisch
✅ E-Mail-Sequenz 30 Tage automatisch
✅ Revenue-Report täglich 07:00 auf Telegram

€97 einmalig. autoincome-ai.vercel.app/supermegabot.html

#Automation #KI #SuperMegaBot`,

  `📝 Neuer Blog-Artikel: Passives Einkommen 2026 — was WIRKLICH funktioniert.

Ehrliche Zahlen, echte Methoden, kein Hype.

Lesen: autoincome-ai.vercel.app/blog

#PassivesEinkommen #OnlineBusiness #2026 #KI #Deutschland`,

  `❓ Umfrage: Habt ihr schon passives Einkommen?

A) Ja, über €500/Monat
B) Ja, unter €500/Monat
C) Ich arbeite daran
D) Noch nicht gestartet

Kommentiert! Ich antworte jedem.

Mein Plan für den Start: autoincome-ai.vercel.app

#PassivesEinkommen #Community`,
];

function twitterOAuth1Sign(method, url, params, consumerSecret, tokenSecret) {
  const allParams = { ...params };
  const sortedPairs = Object.keys(allParams).sort()
    .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(allParams[k])}`)
    .join('&');
  const baseString = [method, encodeURIComponent(url), encodeURIComponent(sortedPairs)].join('&');
  const signingKey = `${encodeURIComponent(consumerSecret)}&${encodeURIComponent(tokenSecret)}`;
  return createHmac('sha1', signingKey).update(baseString).digest('base64');
}

async function postTweet(text) {
  if (!TWITTER_API_KEY || !TWITTER_API_SECRET || !TWITTER_ACCESS_TOKEN || !TWITTER_ACCESS_SECRET) return null;
  const url = 'https://api.twitter.com/2/tweets';
  const nonce = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
  const ts = Math.floor(Date.now() / 1000).toString();
  const oauthParams = {
    oauth_consumer_key: TWITTER_API_KEY,
    oauth_nonce: nonce,
    oauth_signature_method: 'HMAC-SHA1',
    oauth_timestamp: ts,
    oauth_token: TWITTER_ACCESS_TOKEN,
    oauth_version: '1.0',
  };
  const sig = twitterOAuth1Sign('POST', url, oauthParams, TWITTER_API_SECRET, TWITTER_ACCESS_SECRET);
  oauthParams.oauth_signature = sig;
  const authHeader = 'OAuth ' + Object.keys(oauthParams).sort()
    .map(k => `${encodeURIComponent(k)}="${encodeURIComponent(oauthParams[k])}"`)
    .join(', ');
  const r = await fetch(url, {
    method: 'POST',
    headers: { Authorization: authHeader, 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal: AbortSignal.timeout(10000),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`Twitter ${r.status}: ${JSON.stringify(data).substring(0, 150)}`);
  return data?.data?.id;
}

async function resolveUnsplash(keyword, w = 1000, h = 1500) {
  try {
    const r = await fetch(`https://source.unsplash.com/${w}x${h}/?${keyword}`, {
      method: 'HEAD',
      redirect: 'follow',
    });
    if (r.url && r.url.includes('images.unsplash.com')) return r.url;
  } catch {}
  return `https://source.unsplash.com/${w}x${h}/?${keyword}`;
}

// Pinterest Pins
const PINS = [
  {
    title: 'Geld verdienen von Zuhause 2026 — 12 realistische Methoden',
    description: 'Welche Methoden funktionieren wirklich? Ehrlicher Vergleich mit echten Zahlen. KI-Tools, Digistore24, Affiliate Marketing auf Deutsch. Jetzt lesen!',
    link: `${BLOG_URL}/geld-verdienen-zuhause-2026`,
    keyword: 'home,office,laptop,money',
  },
  {
    title: 'Passives Einkommen aufbauen 2026 — Der komplette Guide',
    description: 'Schritt für Schritt zum ersten passiven Einkommen 2026. KI-gestützte Automation, Digistore24, E-Mail-Marketing. Komplett auf Deutsch.',
    link: `${BLOG_URL}/passives-einkommen-aufbauen-2026`,
    keyword: 'entrepreneur,success,growth',
  },
  {
    title: 'KI Business Ideen 2026 — 10 Modelle die jetzt explodieren',
    description: 'Diese 10 KI-Geschäftsmodelle sind 2026 am profitabelsten. Inklusive konkreter Schritt-für-Schritt Anleitung für den deutschen Markt.',
    link: `${BLOG_URL}/ki-business-ideen-2026`,
    keyword: 'technology,ai,business',
  },
  {
    title: 'AI Income Machine Blueprint — €37 einmalig | Vollautomatisch',
    description: '90-Tage-Plan für automatisches Einkommen mit KI. LinkedIn-Bot, E-Mail-Automation, Digistore24 Integration. 60-Tage Geld-zurück-Garantie.',
    link: PRODUCT_URL,
    keyword: 'automation,passive,income',
  },
  {
    title: 'Digistore24 Verkäufer werden 2026 — Alles was du wissen musst',
    description: 'Schritt-für-Schritt: Wie du auf Digistore24 digitale Produkte verkaufst. Kostenloser Start, automatische Auszahlung.',
    link: `${BLOG_URL}/digistore24-verkaefer-werden-2026`,
    keyword: 'digital,marketing,ecommerce',
  },
  {
    title: 'Geld verdienen mit ChatGPT 2026 — 8 bewiesene Methoden',
    description: 'Mit ChatGPT 2026 wirklich Geld verdienen — 8 Methoden die funktionieren. Textagentur, digitale Produkte, SEO-Blog und mehr.',
    link: `${BLOG_URL}/geld-verdienen-mit-chatgpt-2026`,
    keyword: 'chatgpt,ai,writing',
  },
  {
    title: 'Finanziell unabhängig werden 2026 — 5-Stufen-Plan',
    description: 'Der realistische 5-Stufen-Plan zur finanziellen Unabhängigkeit. Von €0 auf €2.000+ passiv pro Monat für den deutschen Markt.',
    link: `${BLOG_URL}/finanziell-unabhaengig-werden-2026`,
    keyword: 'finance,freedom,wealth',
  },
  {
    title: 'Nebenberuflich selbstständig 2026 — ohne Kündigung starten',
    description: 'Wie du sicher nebenberuflich selbstständig wirst ohne deinen Job zu riskieren. Die besten Modelle für Angestellte.',
    link: `${BLOG_URL}/nebenberuflich-selbststaendig-2026`,
    keyword: 'freelance,work,laptop',
  },
];

async function createPinterestPin(pin) {
  const imageUrl = await resolveUnsplash(pin.keyword, 1000, 1500);
  const r = await fetch('https://api.pinterest.com/v5/pins', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${PINTEREST_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      board_id: PINTEREST_BOARD_ID,
      title: pin.title,
      description: pin.description,
      link: pin.link,
      media_source: { source_type: 'image_url', url: imageUrl },
    }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`Pinterest ${r.status}: ${JSON.stringify(data).substring(0, 200)}`);
  return data.id;
}

// TikTok Scripts
const TIKTOK_SCRIPTS = [
  {
    hook: '€111 in 4 Monaten — vollautomatisch. So geht das:',
    voiceScript: 'Ich zeige dir meine Zahlen nach 4 Monaten KI-Automation. €111 passiv verdient, vollautomatisch, keine Werbung. Das System: Digitales Produkt auf Digistore24, LinkedIn-Bot 3x pro Woche, automatische E-Mail-Sequenz. Link in meiner Bio.',
    hashtags: '#PassivesEinkommen #KI #OnlineBusiness #GeldVerdienen #Automatisierung #Deutschland',
  },
  {
    hook: 'Deutsche KI-Creator haben 85% weniger Konkurrenz — Vorteil nutzen:',
    voiceScript: 'Deutsche KI-Creator haben 85% weniger Konkurrenz als englische. Der deutschsprachige Markt hat 100 Millionen Menschen, kaum jemand macht KI-Content auf Deutsch. Das ist dein Vorteil. Mein System — Link in Bio.',
    hashtags: '#KIBusiness #DeutscheCreator #OnlineBusiness #Nische #PassivesEinkommen',
  },
  {
    hook: '2 Stunden Setup → 0 Stunden Arbeit danach. Hier ist wie:',
    voiceScript: '2 Stunden investieren und danach nie wieder manuell arbeiten. Schritt 1: Digistore24 Konto — 30 Minuten. Schritt 2: Digitales Produkt — 45 Minuten. Schritt 3: LinkedIn-Bot — 30 Minuten. Schritt 4: E-Mail-Automation — 15 Minuten. Fertig. Link in Bio.',
    hashtags: '#2Stunden #Automation #KI #Setup #PassivesEinkommen #GeldVerdienen2026',
  },
  {
    hook: 'SuperMegaBot — KI-Automation für €97:',
    voiceScript: 'SuperMegaBot — das vollautomatische KI-System das ich selbst benutze. LinkedIn postet 3x automatisch, Instagram Di/Do/Sa automatisch, E-Mail-Sequenzen täglich, Telegram Revenue Reports. 32 SEO-Artikel inklusive. €97 einmalig, Link in Bio.',
    hashtags: '#SuperMegaBot #KIAutomation #Automatisierung #OnlineBusiness #DigitalNomad',
  },
  {
    hook: '3 Fehler die ich beim passiven Einkommen gemacht habe:',
    voiceScript: '3 Fehler die mich 6 Monate gekostet haben. Fehler 1: Auf Englisch gestartet, falsche Zielgruppe. Fehler 2: Täglich manuell gepostet, nicht skalierbar. Fehler 3: Falsches Produkt, kein Automatisierungspotential. Was funktioniert hat — Link in Bio.',
    hashtags: '#Fehler #Learning #PassivesEinkommen #KI #OnlineBusiness #GeldVerdienen',
  },
];

// YouTube Community Post Templates (8, rotierend Mi/Sa)
const YOUTUBE_POSTS = [
  {
    text: `📊 Update: €111 — vollautomatisch in 4 Monaten\n\nIch teile hier offen was wirklich passiert:\n→ 3 Verkäufe auf Digistore24\n→ 0 Stunden manuelle Arbeit danach\n→ LinkedIn-Bot, Email-Sequenz, Blog-Artikel — alles läuft alleine\n\nDas ist der Proof of Concept. Jetzt skalieren.\n\nMein Blueprint (der Plan hinter diesem System): ${PRODUCT_URL}\n\nWas interessiert euch mehr: Das technische Setup oder die Marketing-Strategie? 👇`,
    topic: 'revenue-update',
  },
  {
    text: `🇩🇪 Warum der deutsche KI-Markt 2026 explodiert (und kaum einer macht mit)\n\nFakten die mich überrascht haben:\n• 85% weniger Konkurrenz als auf Englisch für KI-Themen\n• DACH hat höhere Kaufkraft als US bei Digital-Produkten\n• Deutsche LinkedIn-Nutzer konvertieren 3x besser als andere\n\nIch schreibe seit Monaten auf Deutsch über KI — und die Zahlen bestätigen es.\n\nDen vollständigen Artikel gibts hier: ${BLOG_URL}\n\nSchreibt ihr auch auf Deutsch oder Englisch? Warum? 👇`,
    topic: 'market-analysis',
  },
  {
    text: `🛠️ KI-Tools die ich WIRKLICH täglich nutze (kein Gesponserte)\n\nDie ehrliche Liste:\n✅ Claude für Code & Strategieplanung\n✅ Klaviyo für automatische E-Mails\n✅ Digistore24 für Zahlungsabwicklung\n✅ Vercel für kostenloses Hosting\n✅ Supabase für Datenbank + Blog\n\nWas ich NICHT mehr nutze:\n❌ ChatGPT Plus (zu teuer für den Use Case)\n❌ Zapier (zu langsam, zu teuer)\n❌ Manuelle Social Media Posts\n\nHabt ihr andere Favoriten? 👇`,
    topic: 'tools-list',
  },
  {
    text: `❓ Kurze Frage an euch — bitte ehrlich antworten!\n\nHabt ihr schon passives Einkommen?\n\nA) Ja, über €500/Monat\nB) Ja, unter €500/Monat\nC) Ich arbeite daran\nD) Noch nicht gestartet\n\nIch frage weil ich meinen nächsten Kurs darauf aufbauen möchte — was ist die größte Herausforderung?\n\nKommentiert einfach den Buchstaben + was euch aufhält. Ich antworte jedem! 👇`,
    topic: 'engagement-poll',
  },
  {
    text: `🤖 SuperMegaBot Launch — alle Details die ich bisher nicht geteilt habe\n\nWas ist SuperMegaBot eigentlich?\n→ Ein komplettes KI-Automation System das ich selbst täglich nutze\n→ LinkedIn postet automatisch 3x/Woche\n→ Email-Sequenz läuft 30 Tage lang automatisch\n→ Blog schreibt sich selbst (SEO-optimiert)\n→ Telegram-Reports jeden Morgen\n\nPreis: €97 (Einmalzahlung, kein Abo)\n\nDas komplette System: ${UPSELL_URL}\n\nFragen? Stellt sie hier in den Kommentaren! 👇`,
    topic: 'product-launch',
  },
  {
    text: `💰 50% Affiliate-Provision — so funktioniert es konkret\n\nIhr verdient Geld wenn ich Geld verdiene. So einfach:\n\nBlueprint €37 → ihr bekommt €18,50 pro Verkauf\nSuperMegaBot €97 → ihr bekommt €48,50 pro Verkauf\n\nDigistore24 zahlt wöchentlich auf euer Konto aus.\nKeine Website nötig. Keine Mindestbestellmenge.\n\n10 Verkäufe/Monat = €185–485 passiv.\n\nAlle Details + kostenlose Anmeldung: ${AFFILIATE_URL}\n\nWer ist dabei? Kommentar mit "AFFILIATE"! 👇`,
    topic: 'affiliate-promo',
  },
  {
    text: `📝 Neuer Blog-Artikel: Passives Einkommen 2026 — was wirklich funktioniert\n\nIch habe die letzten Wochen dokumentiert:\n✅ Was hat Einnahmen gebracht?\n✅ Was war Zeitverschwendung?\n✅ Welche Kanäle konvertieren am besten?\n\nSpoiler: LinkedIn und Email sind unschlagbar.\nTikTok? Viel Aufwand, wenig Return.\n\nGanzen Artikel lesen: ${BLOG_URL}\n\nWas ist eure Erfahrung mit verschiedenen Traffic-Quellen? 👇`,
    topic: 'blog-article',
  },
  {
    text: `📈 Wochenrückblick — meine Automatisierungs-Stats\n\nDiese Woche automatisch passiert:\n→ LinkedIn: 3 Posts veröffentlicht, ~2.400 Impressionen\n→ Email-Sequenz: Läuft für alle Subscriber (4 Stufen)\n→ Blog: Wöchentlicher SEO-Artikel erschienen\n→ Telegram: Täglicher Revenue-Report (07:00)\n→ Amazon Affiliate: 2 Posts mit Smart Home Deals\n\nGesamtaufwand meinerseits: ~0 Stunden\n\nWelche repetitiven Tasks würdet ihr gerne automatisieren? 👇`,
    topic: 'weekly-recap',
  },
];

async function tryYouTubePost(text) {
  if (!YOUTUBE_TOKEN) return null;
  try {
    const r = await fetch('https://www.googleapis.com/youtube/v3/communityPosts?part=snippet', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${YOUTUBE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ snippet: { type: 'textPost', textOriginalContent: text } }),
      signal: AbortSignal.timeout(10000),
    });
    if (r.ok) {
      const data = await r.json();
      return { success: true, id: data.id };
    }
    const err = await r.text();
    return { success: false, error: `YT ${r.status}: ${err.substring(0, 100)}` };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function postTikTokViaAPI(script) {
  const r = await fetch('https://open.tiktokapis.com/v2/post/publish/content/init/', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${TIKTOK_TOKEN}`,
      'Content-Type': 'application/json; charset=UTF-8',
    },
    body: JSON.stringify({
      post_info: {
        title: script.hook.substring(0, 150),
        privacy_level: 'PUBLIC_TO_EVERYONE',
        disable_duet: false,
        disable_comment: false,
        disable_stitch: false,
      },
      source_info: {
        source: 'PULL_FROM_URL',
        photo_cover_index: 0,
        photo_images: [
          await resolveUnsplash('business,money,laptop', 1080, 1920),
          await resolveUnsplash('automation,technology', 1080, 1920),
        ],
      },
      post_mode: 'DIRECT_POST',
      media_type: 'PHOTO',
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  const data = await r.json();
  return data?.data?.publish_id;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const hourUTC = now.getUTCHours();
  const results = [];

  // Pinterest: Mo=1, Do=4 at 13:00 UTC
  if ([1, 4].includes(dayOfWeek) && hourUTC === 13) {
    if (PINTEREST_TOKEN && PINTEREST_BOARD_ID) {
      const daySlot = dayOfWeek === 1 ? 0 : 1;
      const idx = (weekNum * 2 + daySlot) % PINS.length;
      const pin = PINS[idx];
      try {
        const pinId = await createPinterestPin(pin);
        await sendTelegram(`✅ Pinterest Pin erstellt!\n📌 Pin ID: ${pinId}\n📝 ${pin.title}`);
        results.push({ platform: 'pinterest', pinId, idx });
      } catch (err) {
        await sendTelegram(`❌ Pinterest fehlgeschlagen: ${err.message.substring(0, 150)}`);
        results.push({ platform: 'pinterest', error: err.message });
      }
    } else {
      await sendTelegram(
        '📌 <b>Pinterest Setup (10 Min):</b>\n\n' +
        '1. developers.pinterest.com → Create App\n' +
        '2. OAuth scope: boards:read,pins:write\n' +
        '3. Board ID aus URL: pinterest.com/username/boardname\n' +
        '4. <code>vercel env add PINTEREST_ACCESS_TOKEN production</code>\n' +
        '5. <code>vercel env add PINTEREST_BOARD_ID production</code>'
      );
      results.push({ platform: 'pinterest', status: 'credentials_missing' });
    }
  }

  // TikTok: Mo=1, Mi=3, Fr=5 at 14:00 UTC
  if ([1, 3, 5].includes(dayOfWeek) && hourUTC === 14) {
    const daySlot = dayOfWeek === 1 ? 0 : dayOfWeek === 3 ? 1 : 2;
    const idx = (weekNum * 3 + daySlot) % TIKTOK_SCRIPTS.length;
    const script = TIKTOK_SCRIPTS[idx];

    if (TIKTOK_TOKEN) {
      try {
        const publishId = await postTikTokViaAPI(script);
        await sendTelegram(`✅ TikTok Post live!\n📱 Publish ID: ${publishId}\n📝 ${script.hook}`);
        results.push({ platform: 'tiktok', publishId, idx });
      } catch (err) {
        await sendTelegram(`⚠️ TikTok API Fehler, sende Skript:\n\n${script.hook}\n\n${script.voiceScript}\n\n${script.hashtags}`);
        results.push({ platform: 'tiktok', mode: 'telegram_fallback', idx });
      }
    } else {
      await sendTelegram(
        `📱 <b>TikTok Skript heute:</b>\n\n` +
        `<b>Hook:</b> ${script.hook}\n\n` +
        `<b>Skript (15 Sek):</b>\n${script.voiceScript}\n\n` +
        `<b>Hashtags:</b>\n${script.hashtags}\n\n` +
        `⏱️ Nur 30 Sek posten: TikTok → + → Video/Text\n` +
        `<i>Für Auto-Post: developers.tiktok.com → Content Posting API → vercel env add TIKTOK_ACCESS_TOKEN</i>`
      );
      results.push({ platform: 'tiktok', mode: 'telegram_script', idx });
    }
  }

  // YouTube Community: Mi=3, Sa=6 at 16:00 UTC
  if ([3, 6].includes(dayOfWeek) && hourUTC === 16) {
    const daySlot = dayOfWeek === 3 ? 0 : 1;
    const idx = (weekNum * 2 + daySlot) % YOUTUBE_POSTS.length;
    const post = YOUTUBE_POSTS[idx];

    const ytResult = await tryYouTubePost(post.text);
    const ytSuccess = ytResult?.success === true;

    if (ytSuccess) {
      await sendTelegram(`✅ YouTube Community Post live!\n📺 Post ID: ${ytResult.id}\n📝 Topic: ${post.topic}`);
      results.push({ platform: 'youtube', postId: ytResult.id, idx });
    } else {
      const errNote = YOUTUBE_TOKEN
        ? `API Fehler: ${ytResult?.error || 'unbekannt'}`
        : 'Kein YOUTUBE_OAUTH_TOKEN gesetzt';
      const tgMsg =
        `📺 <b>YouTube Community Post (manuell posten):</b>\n` +
        `⚠️ ${errNote}\n\n` +
        `→ <b>Jetzt posten:</b> youtube.com/post\n\n` +
        `<b>Text (copy-paste):</b>\n\n${post.text.substring(0, 3500)}`;
      await sendTelegram(tgMsg);
      results.push({ platform: 'youtube', mode: 'telegram_fallback', idx, error: ytResult?.error });
    }
  }

  // Twitter/X: Mo=1, Mi=3, Fr=5 at 15:00 UTC
  if ([1, 3, 5].includes(dayOfWeek) && hourUTC === 15) {
    const daySlot = dayOfWeek === 1 ? 0 : dayOfWeek === 3 ? 1 : 2;
    const idx = (weekNum * 3 + daySlot) % TWEETS.length;
    const tweet = TWEETS[idx];
    if (TWITTER_API_KEY && TWITTER_ACCESS_TOKEN) {
      try {
        const tweetId = await postTweet(tweet);
        await sendTelegram(`✅ Tweet live!\n🐦 ID: ${tweetId}\n📝 ${tweet.substring(0, 80)}...`);
        results.push({ platform: 'twitter', tweetId, idx });
      } catch (err) {
        await sendTelegram(
          `⚠️ Tweet Fehler: ${err.message.substring(0, 100)}\n\n` +
          `Falls 402 CreditsDepleted → developer.twitter.com → Billing → Credits kaufen\n\n` +
          `<b>Tweet (manuell posten):</b>\n${tweet.substring(0, 250)}`
        );
        results.push({ platform: 'twitter', error: err.message, idx });
      }
    } else {
      await sendTelegram(
        `🐦 <b>Tweet heute (manuell posten):</b>\n\n${tweet}\n\n` +
        `Auto-Post: vercel env add TWITTER_API_KEY/SECRET/ACCESS_TOKEN/ACCESS_SECRET production`
      );
      results.push({ platform: 'twitter', mode: 'telegram_fallback', idx });
    }
  }

  return res.status(200).json({ ok: true, results, day: dayOfWeek, hour: hourUTC });
}
