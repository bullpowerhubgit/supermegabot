// Visual Poster: TikTok + Pinterest
// TikTok: Mo/Mi/Fr 14:00 UTC | Pinterest: Mo/Do 13:00 UTC
// TikTok: Photo Post API oder Telegram-Skript
// Pinterest: Pins mit echten Unsplash-Bildern

const TIKTOK_TOKEN = process.env.TIKTOK_ACCESS_TOKEN;
const PINTEREST_TOKEN = process.env.PINTEREST_ACCESS_TOKEN;
const PINTEREST_BOARD_ID = process.env.PINTEREST_BOARD_ID;
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
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
  const results = [];

  // Pinterest: Mo=1, Do=4
  if ([1, 4].includes(dayOfWeek)) {
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

  // TikTok: Mo=1, Mi=3, Fr=5
  if ([1, 3, 5].includes(dayOfWeek)) {
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

  return res.status(200).json({ ok: true, results, day: dayOfWeek });
}
