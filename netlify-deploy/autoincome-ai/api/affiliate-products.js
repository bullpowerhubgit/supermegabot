// Amazon + eBay + AliExpress Affiliate Poster
// Nische: Smart Home / Gadgets (eBay/Amazon/AliExpress = Smart Home per Produktregel)
// Cron: Di/Fr 09:00 UTC
// Kein PA API nötig — direkte Affiliate-Suchlinks + kuratierte Produktbeschreibungen
// Amazon Associate Tag: bullpowerhub-21 | eBay EPN | AliExpress tracking_id: aiitec

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const LINKEDIN_TOKEN = process.env.LINKEDIN_ACCESS_TOKEN;
const LINKEDIN_AUTHOR = process.env.LINKEDIN_PERSON_URN;

const AMAZON_TAG = process.env.AMAZON_ASSOCIATE_TAG || 'bullpowerhub-21';
const EBAY_CAMPAIGN_ID = process.env.EBAY_CAMPAIGN_ID || '';

// Kuratierte Smart Home / Gadgets Deals — rotierend pro Woche
// Amazon: direkte ASIN + Associate Tag (echte Produkte, echte Provision)
const DEALS = [
  {
    topic: 'Smart Home Starter — günstig einsteigen',
    products: [
      {
        name: 'Amazon Echo Dot (5. Gen) — Smarter Lautsprecher mit Alexa',
        platform: 'Amazon',
        asin: 'B09B8YWXDF',
        url: () => `https://www.amazon.de/dp/B09B8YWXDF?tag=${AMAZON_TAG}`,
        priceRange: '€39–€59',
        commission: '~3%',
      },
      {
        name: 'Govee Smart LED Streifen 10m — App-steuerbar, RGB',
        platform: 'Amazon',
        asin: 'B09QY2CBQS',
        url: () => `https://www.amazon.de/dp/B09QY2CBQS?tag=${AMAZON_TAG}`,
        priceRange: '€25–€45',
        commission: '~3%',
      },
      {
        name: 'TP-Link Kasa Smart Plug WLAN — Zeitschaltuhr per App',
        platform: 'Amazon',
        asin: 'B07B8T3L88',
        url: () => `https://www.amazon.de/dp/B07B8T3L88?tag=${AMAZON_TAG}`,
        priceRange: '€15–€25',
        commission: '~3%',
      },
    ],
    ebaySearch: 'smart home set alexa',
    aliSearch: 'smart home starter kit',
  },
  {
    topic: 'Fitness & Wearables 2026 — die besten Tracker',
    products: [
      {
        name: 'Xiaomi Smart Band 9 — Fitness Tracker mit 14 Tagen Akkulaufzeit',
        platform: 'Amazon',
        asin: 'B0CHK7PTJF',
        url: () => `https://www.amazon.de/dp/B0CHK7PTJF?tag=${AMAZON_TAG}`,
        priceRange: '€35–€50',
        commission: '~3%',
      },
      {
        name: 'Garmin vívofit jr. 3 — Aktivitätstracker für Kinder',
        platform: 'Amazon',
        asin: 'B08J5YS1VG',
        url: () => `https://www.amazon.de/dp/B08J5YS1VG?tag=${AMAZON_TAG}`,
        priceRange: '€70–€90',
        commission: '~3%',
      },
    ],
    ebaySearch: 'fitness tracker 2026',
    aliSearch: 'fitness band smart bracelet',
  },
  {
    topic: 'Roboter-Haushaltsgeräte — Putzen ohne Arbeit',
    products: [
      {
        name: 'Eufy RoboVac 11S — Ultradünner Saugroboter (1300Pa)',
        platform: 'Amazon',
        asin: 'B07M9ZH1XG',
        url: () => `https://www.amazon.de/dp/B07M9ZH1XG?tag=${AMAZON_TAG}`,
        priceRange: '€120–€160',
        commission: '~3%',
      },
      {
        name: 'iRobot Roomba i3+ — Auto-Entleerung, Mapping-Funktion',
        platform: 'Amazon',
        asin: 'B08F5SS1P9',
        url: () => `https://www.amazon.de/dp/B08F5SS1P9?tag=${AMAZON_TAG}`,
        priceRange: '€300–€400',
        commission: '~3%',
      },
    ],
    ebaySearch: 'saugroboter roboter staubsauger',
    aliSearch: 'robot vacuum cleaner',
  },
  {
    topic: 'Kabellos & Kabellos — die besten Kopfhörer 2026',
    products: [
      {
        name: 'Sony WH-1000XM5 — Premium Noise Cancelling Kopfhörer',
        platform: 'Amazon',
        asin: 'B09XS7JWHH',
        url: () => `https://www.amazon.de/dp/B09XS7JWHH?tag=${AMAZON_TAG}`,
        priceRange: '€280–€350',
        commission: '~3%',
      },
      {
        name: 'TOZO T6 True Wireless Earbuds — IPX8, 8h Laufzeit',
        platform: 'Amazon',
        asin: 'B07RGZ5NKS',
        url: () => `https://www.amazon.de/dp/B07RGZ5NKS?tag=${AMAZON_TAG}`,
        priceRange: '€20–€30',
        commission: '~3%',
      },
    ],
    ebaySearch: 'bluetooth kopfhörer noise cancelling',
    aliSearch: 'wireless earbuds bluetooth',
  },
  {
    topic: 'Mini-Beamer & Projektoren — Heimkino für jeden',
    products: [
      {
        name: 'Anker Nebula Capsule II — Portabler Projektor mit Android TV',
        platform: 'Amazon',
        asin: 'B08G4TPS71',
        url: () => `https://www.amazon.de/dp/B08G4TPS71?tag=${AMAZON_TAG}`,
        priceRange: '€350–€400',
        commission: '~3%',
      },
      {
        name: 'Vankyo Leisure 3W Mini Beamer — 1080p, WLAN, Bluetooth',
        platform: 'Amazon',
        asin: 'B09MCMZ3XK',
        url: () => `https://www.amazon.de/dp/B09MCMZ3XK?tag=${AMAZON_TAG}`,
        priceRange: '€80–€110',
        commission: '~3%',
      },
    ],
    ebaySearch: 'mini beamer portable projektor',
    aliSearch: 'mini projector portable',
  },
  {
    topic: 'Smarte Beleuchtung — Philips Hue & Alternativen',
    products: [
      {
        name: 'Philips Hue White & Color Starter Set — 3x E27 + Bridge',
        platform: 'Amazon',
        asin: 'B07DHJZMDM',
        url: () => `https://www.amazon.de/dp/B07DHJZMDM?tag=${AMAZON_TAG}`,
        priceRange: '€120–€150',
        commission: '~3%',
      },
      {
        name: 'LIFX A60 Smart Bulb — kein Hub nötig, 16 Mio. Farben',
        platform: 'Amazon',
        asin: 'B01KY02MS4',
        url: () => `https://www.amazon.de/dp/B01KY02MS4?tag=${AMAZON_TAG}`,
        priceRange: '€35–€50',
        commission: '~3%',
      },
    ],
    ebaySearch: 'smart bulb rgb wlan',
    aliSearch: 'smart led bulb wifi',
  },
];

function getEbayAffiliateLink(query) {
  const encoded = encodeURIComponent(query);
  if (EBAY_CAMPAIGN_ID) {
    return `https://rover.ebay.com/rover/1/707-53477-19255-0/1?icep_id=114&ipn=icep&toolid=20004&campid=${EBAY_CAMPAIGN_ID}&mpre=https://www.ebay.de/sch/i.html?_nkw=${encoded}&customid=aiitec`;
  }
  return `https://www.ebay.de/sch/i.html?_nkw=${encoded}`;
}

function getAliExpressLink(query) {
  return `https://de.aliexpress.com/w/wholesale-${encodeURIComponent(query.replace(/\s+/g, '-'))}.html?trafficChannel=affiliate&d=y&CatId=0&SearchText=${encodeURIComponent(query)}&aff_fcid=aiitec&aff_fsk=aiitec&aff_platform=link-c-tool&sk=aiitec&aff_trace_key=aiitec`;
}

async function sendTelegram(msg) {
  if (!TELEGRAM_BOT || !TELEGRAM_CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML', disable_web_page_preview: true }),
    });
  } catch {}
}

async function postLinkedIn(text) {
  if (!LINKEDIN_TOKEN || !LINKEDIN_AUTHOR) return null;
  const r = await fetch('https://api.linkedin.com/v2/ugcPosts', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${LINKEDIN_TOKEN}`,
      'Content-Type': 'application/json',
      'X-Restli-Protocol-Version': '2.0.0',
    },
    body: JSON.stringify({
      author: LINKEDIN_AUTHOR,
      lifecycleState: 'PUBLISHED',
      specificContent: {
        'com.linkedin.ugc.ShareContent': {
          shareCommentary: { text },
          shareMediaCategory: 'NONE',
        },
      },
      visibility: { 'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC' },
    }),
  });
  if (!r.ok) {
    const err = await r.text();
    throw new Error(`LinkedIn ${r.status}: ${err.substring(0, 150)}`);
  }
  return r.headers.get('X-RestLi-Id');
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const daySlot = dayOfWeek === 2 ? 0 : 1;
  const dealIdx = (weekNum * 2 + daySlot) % DEALS.length;
  const deal = DEALS[dealIdx];

  // Build product lines
  const productLines = deal.products.map((p) => {
    const url = p.url();
    return `• <a href="${url}">${p.name}</a>\n  ${p.priceRange} | ${p.platform} | Provision: ${p.commission}`;
  }).join('\n\n');

  const ebayUrl = getEbayAffiliateLink(deal.ebaySearch);
  const aliUrl = getAliExpressLink(deal.aliSearch);

  const tgMsg = `🛒 <b>Affiliate Deals — ${deal.topic}</b>\n\n${productLines}\n\n` +
    `🔍 Mehr Angebote:\n` +
    `• <a href="${ebayUrl}">eBay: ${deal.ebaySearch}</a>\n` +
    `• <a href="${aliUrl}">AliExpress: ${deal.aliSearch}</a>\n\n` +
    `💰 Amazon: ~3% Provision | eBay: ~1-4% | AliExpress: bis 8%`;

  await sendTelegram(tgMsg);

  // LinkedIn Post
  const linkedinText = `🛒 ${deal.topic} — Top Smart Home Deals diese Woche

${deal.products.map((p) => `• ${p.name} (${p.priceRange})\n  → ${p.url()}`).join('\n\n')}

Auch interessant:
→ eBay: ${ebayUrl}
→ AliExpress: ${aliUrl}

Diese Links sind Affiliate-Links — ich erhalte eine kleine Provision bei Kauf, ohne Mehrkosten für euch.

Für vollautomatisches Online-Business aufbauen: autoincome-ai.vercel.app

#SmartHome #Gadgets #Amazon #Deals #AffiliateMarketing #PassivesEinkommen`;

  let linkedinPostId = null;
  try {
    linkedinPostId = await postLinkedIn(linkedinText);
  } catch (err) {
    await sendTelegram(`⚠️ LinkedIn Affiliate Post Fehler: ${err.message.substring(0, 100)}`);
  }

  return res.status(200).json({
    ok: true,
    deal: deal.topic,
    products: deal.products.length,
    linkedinPostId,
    dealIdx,
  });
}
