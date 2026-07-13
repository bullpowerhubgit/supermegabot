// Marketplace Automation: Gumroad + Etsy + Fiverr/Upwork + Affiliate Deals
// Gumroad/Etsy: Mi/Sa 15:00 UTC (?mode=marketplace)
// Fiverr/Upwork: täglich 08:00 UTC (?mode=marketplace)
// Affiliate Deals (Amazon/eBay/AliExpress): Di/Fr 09:00 UTC (?mode=affiliate)

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const GUMROAD_TOKEN = process.env.GUMROAD_ACCESS_TOKEN;
const ETSY_KEY = process.env.ETSY_API_KEY;
const ETSY_TOKEN = process.env.ETSY_ACCESS_TOKEN;
const ETSY_SHOP_ID = process.env.ETSY_SHOP_ID;
const AMAZON_TAG = process.env.AMAZON_ASSOCIATE_TAG || 'bullpowerhub-21';
const EBAY_CAMPAIGN_ID = process.env.EBAY_CAMPAIGN_ID || '';
const LINKEDIN_TOKEN = process.env.LINKEDIN_ACCESS_TOKEN;
const LINKEDIN_AUTHOR = process.env.LINKEDIN_PERSON_URN;
const PRODUCT_URL_37 = 'https://www.checkout-ds24.com/product/668035';
const PRODUCT_URL_97 = 'https://www.checkout-ds24.com/product/668035';

const GUMROAD_PRODUCTS = [
  {
    name: 'AI Income Machine — 90-Day Blueprint (Deutsch)',
    description: `Der vollständige 90-Tage-Aktionsplan für automatisches Einkommen auf Deutsch.

Was du bekommst:
✅ 90-Tage-Roadmap: Schritt für Schritt zum passiven Einkommen
✅ Digistore24 Schritt-für-Schritt-Guide (Setup in 2h)
✅ LinkedIn-Bot Konfiguration (Mo/Mi/Fr automatisch)
✅ Klaviyo E-Mail-Sequenz Vorlagen (4 automatische E-Mails)
✅ Checkliste: Dein erstes digitales Produkt in 24h

Für wen: Deutsche Online-Unternehmer, Anfänger, Freelancer.
60-Tage Geld-zurück-Garantie.`,
    price: 3700,
    currency: 'EUR',
    url_slug: 'ai-income-machine-deutsch',
  },
  {
    name: 'SuperMegaBot — KI-Automation System (Deutsch)',
    description: `Das vollständige KI-Automation System für den deutschen Markt.

Was drin ist:
✅ LinkedIn Auto-Poster (3x/Woche automatisch)
✅ Instagram Auto-Poster (Di/Do/Sa automatisch)
✅ Facebook Auto-Poster (Mo/Mi/Fr automatisch)
✅ Klaviyo E-Mail-Automation (täglich)
✅ Digistore24 Integration
✅ Telegram Revenue Reports (täglich 07:00)
✅ 32 SEO-Blog-Artikel (Deutsch)
✅ 1-Click Deploy auf Railway`,
    price: 9700,
    currency: 'EUR',
    url_slug: 'supermegabot-ki-automation',
  },
];

const ETSY_LISTINGS = [
  {
    title: 'AI Income Machine Blueprint German — Passive Income Automation Guide 2026',
    description: `German language guide for building automated passive income with AI tools.

WHAT YOU GET:
• 90-day action plan (PDF, German language)
• Digistore24 seller setup guide (step-by-step)
• LinkedIn automation templates
• Email marketing sequence (4 automated emails)
• Digital product launch checklist

LANGUAGE: German (Deutsch) — for the DACH market (Germany, Austria, Switzerland)
FORMAT: Instant digital download (PDF)
GUARANTEE: 60-day money-back guarantee

The German market has 85% LESS competition than English for AI content — this is your advantage.

Perfect for: German-speaking entrepreneurs, freelancers, anyone wanting passive income.`,
    price: 3700,
    quantity: 999,
    taxonomy_id: 2078,
    tags: ['passive income', 'AI guide', 'German ebook', 'automation', 'digital product', 'Digistore24', 'online business', 'make money online', 'KI', 'blueprint'],
    who_made: 'i_did',
    when_made: '2020_2024',
    is_supply: false,
    is_digital: true,
  },
];

const UPWORK_KEYWORDS = [
  'KI Automatisierung deutsch',
  'LinkedIn Automation German',
  'Digistore24 setup',
  'passive income automation',
  'email marketing Klaviyo',
  'AI online business german',
];

const AFFILIATE_DEALS = [
  { topic: 'Smart Home Starter — günstig einsteigen', products: [{ name: 'Amazon Echo Dot (5. Gen) — Smarter Lautsprecher mit Alexa', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B09B8YWXDF?tag=${AMAZON_TAG}`, priceRange: '€39–€59', commission: '~3%' }, { name: 'Govee Smart LED Streifen 10m — App-steuerbar, RGB', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B09QY2CBQS?tag=${AMAZON_TAG}`, priceRange: '€25–€45', commission: '~3%' }, { name: 'TP-Link Kasa Smart Plug WLAN — Zeitschaltuhr per App', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B07B8T3L88?tag=${AMAZON_TAG}`, priceRange: '€15–€25', commission: '~3%' }], ebaySearch: 'smart home set alexa', aliSearch: 'smart home starter kit' },
  { topic: 'Fitness & Wearables 2026 — die besten Tracker', products: [{ name: 'Xiaomi Smart Band 9 — Fitness Tracker mit 14 Tagen Akku', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B0CHK7PTJF?tag=${AMAZON_TAG}`, priceRange: '€35–€50', commission: '~3%' }, { name: 'Garmin vívofit jr. 3 — Aktivitätstracker für Kinder', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B08J5YS1VG?tag=${AMAZON_TAG}`, priceRange: '€70–€90', commission: '~3%' }], ebaySearch: 'fitness tracker 2026', aliSearch: 'fitness band smart bracelet' },
  { topic: 'Roboter-Haushaltsgeräte — Putzen ohne Arbeit', products: [{ name: 'Eufy RoboVac 11S — Ultradünner Saugroboter (1300Pa)', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B07M9ZH1XG?tag=${AMAZON_TAG}`, priceRange: '€120–€160', commission: '~3%' }, { name: 'iRobot Roomba i3+ — Auto-Entleerung, Mapping-Funktion', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B08F5SS1P9?tag=${AMAZON_TAG}`, priceRange: '€300–€400', commission: '~3%' }], ebaySearch: 'saugroboter roboter staubsauger', aliSearch: 'robot vacuum cleaner' },
  { topic: 'Kabellos & Kabellos — die besten Kopfhörer 2026', products: [{ name: 'Sony WH-1000XM5 — Premium Noise Cancelling Kopfhörer', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B09XS7JWHH?tag=${AMAZON_TAG}`, priceRange: '€280–€350', commission: '~3%' }, { name: 'TOZO T6 True Wireless Earbuds — IPX8, 8h Laufzeit', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B07RGZ5NKS?tag=${AMAZON_TAG}`, priceRange: '€20–€30', commission: '~3%' }], ebaySearch: 'bluetooth kopfhörer noise cancelling', aliSearch: 'wireless earbuds bluetooth' },
  { topic: 'Mini-Beamer & Projektoren — Heimkino für jeden', products: [{ name: 'Anker Nebula Capsule II — Portabler Projektor mit Android TV', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B08G4TPS71?tag=${AMAZON_TAG}`, priceRange: '€350–€400', commission: '~3%' }, { name: 'Vankyo Leisure 3W Mini Beamer — 1080p, WLAN, Bluetooth', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B09MCMZ3XK?tag=${AMAZON_TAG}`, priceRange: '€80–€110', commission: '~3%' }], ebaySearch: 'mini beamer portable projektor', aliSearch: 'mini projector portable' },
  { topic: 'Smarte Beleuchtung — Philips Hue & Alternativen', products: [{ name: 'Philips Hue White & Color Starter Set — 3x E27 + Bridge', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B07DHJZMDM?tag=${AMAZON_TAG}`, priceRange: '€120–€150', commission: '~3%' }, { name: 'LIFX A60 Smart Bulb — kein Hub nötig, 16 Mio. Farben', platform: 'Amazon', url: () => `https://www.amazon.de/dp/B01KY02MS4?tag=${AMAZON_TAG}`, priceRange: '€35–€50', commission: '~3%' }], ebaySearch: 'smart bulb rgb wlan', aliSearch: 'smart led bulb wifi' },
];

function getEbayLink(query) {
  const enc = encodeURIComponent(query);
  if (EBAY_CAMPAIGN_ID) return `https://rover.ebay.com/rover/1/707-53477-19255-0/1?icep_id=114&ipn=icep&toolid=20004&campid=${EBAY_CAMPAIGN_ID}&mpre=https://www.ebay.de/sch/i.html?_nkw=${enc}&customid=aiitec`;
  return `https://www.ebay.de/sch/i.html?_nkw=${enc}`;
}
function getAliLink(query) {
  return `https://de.aliexpress.com/w/wholesale-${encodeURIComponent(query.replace(/\s+/g, '-'))}.html?SearchText=${encodeURIComponent(query)}`;
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
    headers: { Authorization: `Bearer ${LINKEDIN_TOKEN}`, 'Content-Type': 'application/json', 'X-Restli-Protocol-Version': '2.0.0' },
    body: JSON.stringify({ author: LINKEDIN_AUTHOR, lifecycleState: 'PUBLISHED', specificContent: { 'com.linkedin.ugc.ShareContent': { shareCommentary: { text }, shareMediaCategory: 'NONE' } }, visibility: { 'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC' } }),
  });
  if (!r.ok) throw new Error(`LinkedIn ${r.status}: ${(await r.text()).substring(0, 150)}`);
  return r.headers.get('X-RestLi-Id');
}

async function handleAffiliate(res) {
  if (!EBAY_CAMPAIGN_ID) await sendTelegram('⚠️ affiliate-products: EBAY_CAMPAIGN_ID fehlt → eBay-Links ohne Provision! Setze EBAY_CAMPAIGN_ID in Vercel ENV.');
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const daySlot = now.getUTCDay() === 2 ? 0 : 1;
  const deal = AFFILIATE_DEALS[(weekNum * 2 + daySlot) % AFFILIATE_DEALS.length];
  const productLines = deal.products.map(p => `• <a href="${p.url()}">${p.name}</a>\n  ${p.priceRange} | ${p.platform} | Provision: ${p.commission}`).join('\n\n');
  const ebayUrl = getEbayLink(deal.ebaySearch);
  const aliUrl  = getAliLink(deal.aliSearch);
  await sendTelegram(`🛒 <b>Affiliate Deals — ${deal.topic}</b>\n\n${productLines}\n\n🔍 Mehr Angebote:\n• <a href="${ebayUrl}">eBay: ${deal.ebaySearch}</a>\n• <a href="${aliUrl}">AliExpress: ${deal.aliSearch}</a>\n\n💰 Amazon: ~3% Provision | eBay: ~1-4% | AliExpress: bis 8%`);
  const linkedinText = `🛒 ${deal.topic} — Top Smart Home Deals diese Woche\n\n${deal.products.map(p => `• ${p.name} (${p.priceRange})\n  → ${p.url()}`).join('\n\n')}\n\nAuch interessant:\n→ eBay: ${ebayUrl}\n→ AliExpress: ${aliUrl}\n\nDiese Links sind Affiliate-Links — ich erhalte eine kleine Provision bei Kauf, ohne Mehrkosten für euch.\n\nFür vollautomatisches Online-Business aufbauen: autoincome-ai.vercel.app\n\n#SmartHome #Gadgets #Amazon #Deals #AffiliateMarketing #PassivesEinkommen`;
  let linkedinPostId = null;
  try { linkedinPostId = await postLinkedIn(linkedinText); } catch (err) { await sendTelegram(`⚠️ LinkedIn Affiliate Post Fehler: ${err.message.substring(0, 100)}`); }
  return res.status(200).json({ ok: true, deal: deal.topic, products: deal.products.length, linkedinPostId });
}

async function gumroadListProducts() {
  const r = await fetch('https://api.gumroad.com/v2/products', {
    headers: { Authorization: `Bearer ${GUMROAD_TOKEN}` },
  });
  if (!r.ok) return [];
  const data = await r.json();
  return data.products || [];
}

async function gumroadCreateProduct(product) {
  const body = new URLSearchParams({
    name: product.name,
    description: product.description,
    price: product.price,
    currency: product.currency,
    url: product.url_slug,
    published: 'true',
  });
  const r = await fetch('https://api.gumroad.com/v2/products', {
    method: 'POST',
    headers: { Authorization: `Bearer ${GUMROAD_TOKEN}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  const data = await r.json();
  if (!data.success) throw new Error(JSON.stringify(data).substring(0, 200));
  return data.product;
}

async function gumroadCreateCoupon(productId, code, amountOff) {
  const body = new URLSearchParams({ offer_code: code, amount_off: amountOff, max_purchase_count: '10' });
  const r = await fetch(`https://api.gumroad.com/v2/products/${productId}/offer_codes`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${GUMROAD_TOKEN}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  return (await r.json()).offer_code;
}

async function etsyCreateListing(listing) {
  const r = await fetch(`https://openapi.etsy.com/v3/application/shops/${ETSY_SHOP_ID}/listings`, {
    method: 'POST',
    headers: {
      'x-api-key': ETSY_KEY,
      Authorization: `Bearer ${ETSY_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ...listing, shipping_profile_id: 0, return_policy_id: 0, listing_type: 'download' }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(JSON.stringify(data).substring(0, 200));
  return data;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== (process.env.CRON_SECRET || 'bullpower2026')) return res.status(401).json({ error: 'unauthorized' });

  const mode = req.query.mode || 'marketplace';
  if (mode === 'affiliate') return handleAffiliate(res);

  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const results = [];

  // --- FIVERR/UPWORK: täglich 08:00 UTC (Mo–Fr) ---
  if (dayOfWeek >= 1 && dayOfWeek <= 5) {
    if (dayOfWeek === 1) {
      // Montag: Fiverr Gig Update-Erinnerung
      await sendTelegram(
        `🟢 <b>Fiverr Wochentask (Montag):</b>\n\n` +
        `Fiverr.com → Gigs → "Update" klicken (erhöht Ranking)\n` +
        `Gig Titel: "I will set up a complete AI automation system for your German online business"\n` +
        `Preis: $97 | 5 Tage Lieferung\n\n` +
        `Noch kein Gig? gumroad.com/l/ai-income-machine-deutsch als Basis nutzen!`
      );
      results.push({ platform: 'fiverr', action: 'weekly_reminder' });
    }
    const kwIdx = now.getUTCDate() % UPWORK_KEYWORDS.length;
    await sendTelegram(
      `💼 <b>Upwork Tipp:</b>\n` +
      `Suche: "${UPWORK_KEYWORDS[kwIdx]}"\n` +
      `→ 2-3 Proposals mit SuperMegaBot-Angebot schicken\n` +
      `→ upwork.com/nx/find-work/?q=${encodeURIComponent(UPWORK_KEYWORDS[kwIdx])}`
    );
    results.push({ platform: 'upwork', keyword: UPWORK_KEYWORDS[kwIdx] });
  }

  // --- GUMROAD + ETSY: Mi=3 und Sa=6 ---
  if ([3, 6].includes(dayOfWeek)) {
    // Gumroad
    if (GUMROAD_TOKEN) {
      try {
        const existing = await gumroadListProducts();
        const existingNames = existing.map((p) => p.name);
        let newCount = 0;
        for (const prod of GUMROAD_PRODUCTS) {
          if (!existingNames.includes(prod.name)) {
            const created = await gumroadCreateProduct(prod);
            await gumroadCreateCoupon(created.id, 'LAUNCH10', 10);
            await sendTelegram(`✅ Gumroad Produkt erstellt: ${created.name}\n🔗 gumroad.com/l/${prod.url_slug}`);
            newCount++;
          }
        }
        if (newCount === 0 && existing.length > 0) {
          const weekCode = `W${now.toISOString().slice(2, 10).replace(/-/g, '')}`;
          await gumroadCreateCoupon(existing[0].id, weekCode, 500);
          await sendTelegram(`🎟️ Gumroad Coupon: ${weekCode} (€5 Rabatt) für ${existing[0].name}`);
        }
        results.push({ platform: 'gumroad', existing: existing.length });
      } catch (err) {
        await sendTelegram(`⚠️ Gumroad Fehler: ${err.message.substring(0, 150)}`);
        results.push({ platform: 'gumroad', error: err.message });
      }
    } else {
      await sendTelegram(
        `💰 <b>Gumroad Setup:</b>\n` +
        `1. gumroad.com/signup\n` +
        `2. app.gumroad.com/settings/advanced → API-Key\n` +
        `3. <code>vercel env add GUMROAD_ACCESS_TOKEN production</code>`
      );
    }

        // Etsy: Accounts gesperrt — kein Etsy möglich
    results.push({ platform: 'etsy', status: 'skipped_accounts_banned' });
  }

  return res.status(200).json({ ok: true, results, day: dayOfWeek });
}
