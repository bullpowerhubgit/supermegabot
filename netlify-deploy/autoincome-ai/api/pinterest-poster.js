// Pinterest Auto-Poster — Pins mit Blog-Artikel Links
// Cron: Mo/Do 13:00 UTC
// Benötigt: PINTEREST_ACCESS_TOKEN + PINTEREST_BOARD_ID
// Setup: developers.pinterest.com → Create App → OAuth → Board ID aus URL

const PINTEREST_TOKEN = process.env.PINTEREST_ACCESS_TOKEN;
const PINTEREST_BOARD_ID = process.env.PINTEREST_BOARD_ID;
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';

// Pinterest Pins — rotierend (Blog-Artikel als Pins)
const PINS = [
  {
    title: 'Geld verdienen von Zuhause 2026 — 12 realistische Methoden',
    description: 'Welche Methoden funktionieren wirklich? Ehrlicher Vergleich mit echten Zahlen. KI-Tools, Digistore24, Affiliate Marketing und das AI Income Machine System auf Deutsch. Jetzt lesen!',
    link: `${BLOG_URL}/geld-verdienen-zuhause-2026`,
    imageUrl: 'https://picsum.photos/seed/pin-ki1/1000/1500',
  },
  {
    title: 'Passives Einkommen aufbauen 2026 — Der komplette Guide',
    description: 'Schritt für Schritt zum ersten passiven Einkommen 2026. KI-gestützte Automation, Digistore24, E-Mail-Marketing. Komplett auf Deutsch. Blueprint für €37.',
    link: `${BLOG_URL}/passives-einkommen-aufbauen-2026`,
    imageUrl: 'https://picsum.photos/seed/pin-passive2/1000/1500',
  },
  {
    title: 'KI Business Ideen 2026 — 10 Modelle die jetzt explodieren',
    description: 'Diese 10 KI-Geschäftsmodelle sind 2026 am profitabelsten. Welche du auch als Anfänger starten kannst. Inklusive konkreter Schritt-für-Schritt Anleitung.',
    link: `${BLOG_URL}/ki-business-ideen-2026`,
    imageUrl: 'https://picsum.photos/seed/pin-ki-biz3/1000/1500',
  },
  {
    title: 'Digistore24 Verkäufer werden 2026 — Alles was du wissen musst',
    description: 'Schritt-für-Schritt: Wie du auf Digistore24 digitale Produkte verkaufst und das Affiliate-Netzwerk nutzt. Kostenloser Start, automatische Auszahlung.',
    link: `${BLOG_URL}/digistore24-verkaefer-werden-2026`,
    imageUrl: 'https://picsum.photos/seed/pin-ds24-4/1000/1500',
  },
  {
    title: 'AI Income Machine Blueprint — €37 einmalig | Vollautomatisch',
    description: '90-Tage-Plan für automatisches Einkommen mit KI. LinkedIn-Bot, E-Mail-Automation, Digistore24 Integration. 60-Tage Geld-zurück-Garantie. Jetzt für €37.',
    link: PRODUCT_URL,
    imageUrl: 'https://picsum.photos/seed/pin-product5/1000/1500',
  },
  {
    title: 'Nebenberuflich selbstständig 2026 — ohne Kündigung starten',
    description: 'Wie du sicher nebenberuflich selbstständig wirst ohne deinen Job zu riskieren. Die besten Modelle für Angestellte. Mit echten Zahlen und konkretem Plan.',
    link: `${BLOG_URL}/nebenberuflich-selbststaendig-2026`,
    imageUrl: 'https://picsum.photos/seed/pin-neben6/1000/1500',
  },
  {
    title: 'Geld verdienen mit ChatGPT 2026 — 8 bewiesene Methoden',
    description: 'Mit ChatGPT 2026 wirklich Geld verdienen — 8 Methoden die funktionieren. Textagentur, digitale Produkte, SEO-Blog, YouTube-Skripte und mehr.',
    link: `${BLOG_URL}/geld-verdienen-mit-chatgpt-2026`,
    imageUrl: 'https://picsum.photos/seed/pin-chatgpt7/1000/1500',
  },
  {
    title: 'Finanziell unabhängig werden 2026 — 5-Stufen-Plan',
    description: 'Der realistische 5-Stufen-Plan zur finanziellen Unabhängigkeit. Von €0 auf €2.000+ passiv pro Monat. Schritt für Schritt erklärt für den deutschen Markt.',
    link: `${BLOG_URL}/finanziell-unabhaengig-werden-2026`,
    imageUrl: 'https://picsum.photos/seed/pin-finanz8/1000/1500',
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

async function createPin(title, description, link, imageUrl) {
  const r = await fetch('https://api.pinterest.com/v5/pins', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${PINTEREST_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      board_id: PINTEREST_BOARD_ID,
      title,
      description,
      link,
      media_source: {
        source_type: 'image_url',
        url: imageUrl,
      },
    }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`Pinterest ${r.status}: ${JSON.stringify(data).substring(0, 300)}`);
  return data.id;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  if (!PINTEREST_TOKEN || !PINTEREST_BOARD_ID) {
    await sendTelegram(
      '❌ Pinterest Poster: Credentials fehlen!\n\n' +
      'Setup (5 Min):\n' +
      '1. developers.pinterest.com → Create App\n' +
      '2. OAuth: pinterest.com/oauth/?response_type=code&client_id=...&scope=boards:read,pins:write\n' +
      '3. Board ID aus URL: pinterest.com/username/board-name/ → letzter Teil\n' +
      '4. vercel env add PINTEREST_ACCESS_TOKEN\n' +
      '5. vercel env add PINTEREST_BOARD_ID'
    );
    return res.status(500).json({ error: 'Pinterest credentials not set' });
  }

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const daySlot = dayOfWeek === 1 ? 0 : 1;
  const pinIdx = (weekNum * 2 + daySlot) % PINS.length;
  const pin = PINS[pinIdx];

  let pinId;
  try {
    pinId = await createPin(pin.title, pin.description, pin.link, pin.imageUrl);
  } catch (err) {
    await sendTelegram(`❌ Pinterest Pin fehlgeschlagen: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ error: err.message });
  }

  await sendTelegram(
    `✅ Pinterest Pin erstellt!\n📌 Pin ID: ${pinId}\n📝 ${pin.title}\n🔗 ${pin.link}`
  );
  return res.status(200).json({ ok: true, pinId, pinTitle: pin.title });
}
