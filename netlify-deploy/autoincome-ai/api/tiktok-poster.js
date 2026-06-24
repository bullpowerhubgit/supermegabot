// TikTok Content Scheduler
// Cron: Mo/Mi/Fr 14:00 UTC
// TikTok API: video posts brauchen echte Video-Datei
// Strategie: TikTok Photo Post (Text-Slides) via TikTok Content Posting API
// ODER: Telegram-Skript für 30-Sekunden-Manual-Post
// Benötigt: TIKTOK_ACCESS_TOKEN (TikTok for Developers → Content Posting API)

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const TIKTOK_TOKEN = process.env.TIKTOK_ACCESS_TOKEN;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';

// TikTok Content — 15-Sekunden Skripte die Rudolf direkt einsprechen kann
// ODER als Text-Slides bei Photo Posts
const TIKTOK_SCRIPTS = [
  {
    hook: '€111 in 4 Monaten — vollautomatisch. So geht das:',
    slides: [
      '€111 passiv verdient',
      'Vollautomatisch mit KI',
      '0 Werbeanzeigen',
      'So hab ich es gemacht:',
      '1. Digitales Produkt erstellt',
      '2. LinkedIn-Bot aufgesetzt',
      '3. E-Mails automatisiert',
      '4. Digistore24 verkauft',
      'Blueprint für €37 ↗',
      'Link in Bio 🔗',
    ],
    hashtags: '#PassivesEinkommen #KI #OnlineBusiness #GeldVerdienen #Automatisierung #Deutschland',
    voiceScript: `Ich zeige dir heute meine Zahlen nach 4 Monaten KI-Automation.
€111 passiv verdient — vollautomatisch. Keine Werbung, kein manuelles Posten.
Das System: Ein digitales Produkt auf Digistore24, ein LinkedIn-Bot der 3x pro Woche postet,
und eine automatische E-Mail-Sequenz die für mich verkauft.
Der komplette 90-Day Blueprint — Link in meiner Bio.`,
  },
  {
    hook: 'Deutsche KI-Creator haben 85% weniger Konkurrenz — Vorteil nutzen:',
    slides: [
      'Deutsche KI-Creator',
      '85% weniger Konkurrenz',
      'als auf Englisch',
      'Gleiche Kaufkraft',
      'Gleicher Markt',
      'Das nutze ich:',
      '→ Blog auf Deutsch',
      '→ LinkedIn auf Deutsch',
      '→ E-Mails auf Deutsch',
      'Starte JETZT — Link in Bio',
    ],
    hashtags: '#KIBusiness #DeutscheCreator #OnlineBusiness #Nische #PassivesEinkommen',
    voiceScript: `Wusstest du? Deutsche KI-Creator haben 85 Prozent weniger Konkurrenz als englische.
Der deutschsprachige Markt hat 100 Millionen Menschen — und kaum jemand macht KI-Content auf Deutsch.
Das ist dein Vorteil. Ich baue genau das gerade auf. Mein System — Link in Bio.`,
  },
  {
    hook: '3 Fehler die ich beim passiven Einkommen gemacht habe:',
    slides: [
      '3 Fehler die ich machte',
      'Fehler 1:',
      'Auf Englisch gestartet',
      '(falsche Zielgruppe)',
      'Fehler 2:',
      'Kein Automation Setup',
      '(täglich manuell posten)',
      'Fehler 3:',
      'Falsches Produkt',
      'Was hat funktioniert?',
      'Blueprint €37 — Link in Bio',
    ],
    hashtags: '#Fehler #Lerning #PassivesEinkommen #KI #OnlineBusiness #GeldVerdienen',
    voiceScript: `Drei Fehler die mich 6 Monate gekostet haben.
Fehler eins: Ich startete auf Englisch — falsche Zielgruppe, zu viel Konkurrenz.
Fehler zwei: Ich postete täglich manuell — nicht skalierbar.
Fehler drei: Falsches Produkt, kein Automatisierungspotential.
Was hat funktioniert? Der komplette Weg — Link in Bio.`,
  },
  {
    hook: '2 Stunden Setup → 0 Stunden Arbeit danach. Hier ist wie:',
    slides: [
      '2 Stunden Setup',
      '→ 0 Stunden Arbeit',
      'Schritt 1 (30 Min):',
      'Digistore24 Konto',
      'Schritt 2 (45 Min):',
      'Produkt hochladen',
      'Schritt 3 (30 Min):',
      'LinkedIn-Bot aktivieren',
      'Schritt 4 (15 Min):',
      'E-Mail-Automation an',
      'Fertig! Jetzt wartet man',
      'Blueprint €37 — Link in Bio',
    ],
    hashtags: '#2Stunden #Automation #KI #Setup #PassivesEinkommen #GeldVerdienen2026',
    voiceScript: `Was wäre wenn du 2 Stunden investierst und danach nie wieder manuell arbeiten musst?
Schritt 1: Digistore24 Konto — 30 Minuten.
Schritt 2: Digitales Produkt hochladen — 45 Minuten.
Schritt 3: LinkedIn-Bot aktivieren — 30 Minuten.
Schritt 4: E-Mail-Automation einrichten — 15 Minuten.
Das war's. Jetzt läuft alles von selbst. Den genauen Plan — Link in Bio.`,
  },
  {
    hook: 'SuperMegaBot — KI-Automation für €97:',
    slides: [
      'SuperMegaBot',
      'KI-Automation System',
      'Was du bekommst:',
      '✅ LinkedIn Auto-Post',
      '✅ Instagram Auto-Post',
      '✅ E-Mail-Automation',
      '✅ Digistore24 Setup',
      '✅ Telegram Reports',
      '✅ 32 SEO-Artikel',
      '€97 einmalig',
      'Link in Bio →',
    ],
    hashtags: '#SuperMegaBot #KIAutomation #Automatisierung #OnlineBusiness #DigitalNomad',
    voiceScript: `SuperMegaBot — das vollautomatische KI-System das ich selbst benutze.
LinkedIn postet 3x pro Woche automatisch. Instagram postet Di, Do, Sa automatisch.
E-Mail-Sequenzen laufen täglich. Digistore24 Integration inklusive.
Täglich kommt ein Telegram-Report mit den Verkaufszahlen.
Und 32 SEO-Artikel für deinen Blog sind auch dabei.
€97 einmalig — Link in Bio.`,
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

async function postTikTokPhotoPost(slides, caption) {
  if (!TIKTOK_TOKEN) return null;
  // TikTok Content Posting API — Photo Post (requires video or photo media)
  // Phase 1: Initialize upload
  const initResp = await fetch('https://open.tiktokapis.com/v2/post/publish/content/init/', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${TIKTOK_TOKEN}`,
      'Content-Type': 'application/json; charset=UTF-8',
    },
    body: JSON.stringify({
      post_info: {
        title: caption.substring(0, 150),
        privacy_level: 'PUBLIC_TO_EVERYONE',
        disable_duet: false,
        disable_comment: false,
        disable_stitch: false,
      },
      source_info: {
        source: 'PULL_FROM_URL',
        photo_cover_index: 0,
        photo_images: slides.map((_, i) =>
          `https://picsum.photos/seed/tiktok-${Date.now()}-${i}/1080/1920`
        ),
      },
      post_mode: 'DIRECT_POST',
      media_type: 'PHOTO',
    }),
  });
  if (!initResp.ok) {
    const err = await initResp.text();
    throw new Error(`TikTok init failed: ${err.substring(0, 200)}`);
  }
  const initData = await initResp.json();
  return initData?.data?.publish_id;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const daySlot = dayOfWeek === 1 ? 0 : dayOfWeek === 3 ? 1 : 2;
  const scriptIdx = (weekNum * 3 + daySlot) % TIKTOK_SCRIPTS.length;
  const script = TIKTOK_SCRIPTS[scriptIdx];

  const caption = `${script.hook}\n\n${script.hashtags}`;

  // Try TikTok API first
  if (TIKTOK_TOKEN) {
    try {
      const publishId = await postTikTokPhotoPost(script.slides, caption);
      await sendTelegram(
        `✅ TikTok Photo Post veröffentlicht!\n📱 Publish ID: ${publishId}\n📝 ${script.hook}`
      );
      return res.status(200).json({ ok: true, publishId, scriptIdx });
    } catch (err) {
      await sendTelegram(`⚠️ TikTok API Fehler: ${err.message.substring(0, 150)}\n\nManual-Post Skript folgt:`);
    }
  }

  // Fallback: Telegram Skript für manuelle Posting (30 Sekunden)
  const slidesText = script.slides.map((s, i) => `Slide ${i + 1}: ${s}`).join('\n');
  await sendTelegram(
    `📱 <b>TikTok Content heute (${now.toLocaleDateString('de-DE')}):</b>\n\n` +
    `<b>Hook:</b> ${script.hook}\n\n` +
    `<b>Voice Script (15 Sek):</b>\n${script.voiceScript}\n\n` +
    `<b>Slides:</b>\n${slidesText}\n\n` +
    `<b>Hashtags:</b>\n${script.hashtags}\n\n` +
    `⏱️ TikTok öffnen → + → Foto → Text-Slides kopieren → Posten\n` +
    `<i>TikTok API Token einrichten: developers.tiktok.com → Content Posting API → vercel env add TIKTOK_ACCESS_TOKEN</i>`
  );

  return res.status(200).json({ ok: true, mode: 'telegram_script', scriptIdx });
}
