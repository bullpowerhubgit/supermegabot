// Amazon + eBay + AliExpress Affiliate Auto-Poster
// Nische: Smart Home / Gadgets (per Produktregel: eBay/Amazon/AliExpress = Smart Home)
// Cron: Di/Fr 09:00 UTC
// Postet Affiliate-Produkte zu LinkedIn + Telegram
// Amazon PA API + eBay Browse API + AliExpress DataIO

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;

// Amazon Product Advertising API v5
const AMAZON_ACCESS_KEY = process.env.AMAZON_ACCESS_KEY;
const AMAZON_SECRET_KEY = process.env.AMAZON_SECRET_KEY;
const AMAZON_ASSOCIATE_TAG = process.env.AMAZON_ASSOCIATE_TAG || 'aiitec-21';
const AMAZON_REGION = 'de';
const AMAZON_HOST = 'webservices.amazon.de';

// eBay Browse API
const EBAY_APP_ID = process.env.EBAY_APP_ID;
const EBAY_CAMPAIGN_ID = process.env.EBAY_CAMPAIGN_ID;
const EBAY_AFFILIATE_CUSTOM_ID = process.env.EBAY_AFFILIATE_CUSTOM_ID || 'aiitec';

// AliExpress DataIO API
const ALIEXPRESS_APP_KEY = process.env.ALIEXPRESS_APP_KEY;
const ALIEXPRESS_ACCESS_TOKEN = process.env.ALIEXPRESS_ACCESS_TOKEN;

// LinkedIn für Affiliate Posts
const LINKEDIN_TOKEN = process.env.LINKEDIN_ACCESS_TOKEN;
const LINKEDIN_AUTHOR = process.env.LINKEDIN_PERSON_URN;

// Smart Home & Gadgets Keywords (Nischen-Regel: eBay/Amazon/AliExpress = Smart Home)
const PRODUCT_KEYWORDS = [
  { keyword: 'Smart Home Starter Set', category: 'Echo Dot OR Zigbee', asin_fallback: 'B09B8YWXDF' },
  { keyword: 'Fitness Tracker 2026', category: 'Wearables', asin_fallback: 'B0CHK7PTJF' },
  { keyword: 'Mini Beamer portabel', category: 'Electronics', asin_fallback: 'B09MCMZ3XK' },
  { keyword: 'Smart Plug Steckdose WLAN', category: 'Smart Home', asin_fallback: 'B07S1BMMSS' },
  { keyword: 'Roboter Staubsauger', category: 'Home Appliances', asin_fallback: 'B08QKNKZPF' },
  { keyword: 'Kabellose Kopfhörer', category: 'Audio', asin_fallback: 'B07Q9MJKBV' },
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

// Amazon PA API Signatur (AWS4-HMAC-SHA256)
async function amazonSign(method, path, payload, headers) {
  const crypto = await import('crypto');
  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, '').slice(0, 15) + 'Z';
  const dateStamp = amzDate.slice(0, 8);
  const service = 'ProductAdvertisingAPI';
  const region = AMAZON_REGION;

  const signedHeaders = 'content-encoding;content-type;host;x-amz-date;x-amz-target';
  const canonicalHeaders =
    `content-encoding:amz-1.0\ncontent-type:application/json; charset=utf-8\nhost:${AMAZON_HOST}\nx-amz-date:${amzDate}\nx-amz-target:com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems\n`;

  const payloadHash = crypto.createHash('sha256').update(payload).digest('hex');
  const canonicalRequest = [method, path, '', canonicalHeaders, signedHeaders, payloadHash].join('\n');
  const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;
  const stringToSign = `AWS4-HMAC-SHA256\n${amzDate}\n${credentialScope}\n${crypto.createHash('sha256').update(canonicalRequest).digest('hex')}`;

  function hmac(key, data) {
    return crypto.createHmac('sha256', key).update(data).digest();
  }
  const signingKey = hmac(hmac(hmac(hmac(`AWS4${AMAZON_SECRET_KEY}`, dateStamp), region), service), 'aws4_request');
  const signature = crypto.createHmac('sha256', signingKey).update(stringToSign).digest('hex');

  return {
    ...headers,
    'X-Amz-Date': amzDate,
    Authorization: `AWS4-HMAC-SHA256 Credential=${AMAZON_ACCESS_KEY}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`,
  };
}

async function searchAmazonProducts(keyword) {
  if (!AMAZON_ACCESS_KEY || !AMAZON_SECRET_KEY) return null;
  const payload = JSON.stringify({
    Keywords: keyword,
    Resources: ['ItemInfo.Title', 'Offers.Listings.Price', 'Images.Primary.Medium', 'DetailPageURL'],
    PartnerTag: AMAZON_ASSOCIATE_TAG,
    PartnerType: 'Associates',
    Marketplace: 'www.amazon.de',
    ItemCount: 3,
  });
  try {
    const path = '/paapi5/searchitems';
    const headers = await amazonSign('POST', path, payload, {
      'Content-Encoding': 'amz-1.0',
      'Content-Type': 'application/json; charset=utf-8',
      Host: AMAZON_HOST,
      'X-Amz-Target': 'com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems',
    });
    const r = await fetch(`https://${AMAZON_HOST}${path}`, { method: 'POST', headers, body: payload });
    if (!r.ok) return null;
    const data = await r.json();
    return data.SearchResult?.Items || null;
  } catch {
    return null;
  }
}

async function getAmazonDirectLink(keyword) {
  const encoded = encodeURIComponent(keyword);
  return `https://www.amazon.de/s?k=${encoded}&tag=${AMAZON_ASSOCIATE_TAG}`;
}

async function searchEbayProducts(keyword) {
  if (!EBAY_APP_ID) return null;
  try {
    const r = await fetch(
      `https://api.ebay.com/buy/browse/v1/item_summary/search?q=${encodeURIComponent(keyword)}&limit=3&filter=deliveryCountry:DE,currency:EUR`,
      {
        headers: {
          Authorization: `Bearer ${EBAY_APP_ID}`,
          'X-EBAY-C-MARKETPLACE-ID': 'EBAY_DE',
          'Content-Language': 'de-DE',
        },
      }
    );
    if (!r.ok) return null;
    const data = await r.json();
    return data.itemSummaries || null;
  } catch {
    return null;
  }
}

function getEbayAffiliateLink(itemId) {
  if (!EBAY_CAMPAIGN_ID) return `https://www.ebay.de/itm/${itemId}`;
  return `https://rover.ebay.com/rover/1/707-53477-19255-0/1?icep_id=114&ipn=icep&toolid=20004&campid=${EBAY_CAMPAIGN_ID}&mpre=https://www.ebay.de/itm/${itemId}&customid=${EBAY_AFFILIATE_CUSTOM_ID}`;
}

async function searchAliExpressProducts(keyword) {
  if (!ALIEXPRESS_APP_KEY || !ALIEXPRESS_ACCESS_TOKEN) return null;
  try {
    const params = new URLSearchParams({
      app_key: ALIEXPRESS_APP_KEY,
      access_token: ALIEXPRESS_ACCESS_TOKEN,
      keywords: keyword,
      local_country: 'DE',
      local_currency: 'EUR',
      page_size: '3',
      target_currency: 'EUR',
      target_language: 'DE',
      tracking_id: 'aiitec',
      timestamp: Date.now().toString(),
    });
    const r = await fetch(
      `https://api-sg.aliexpress.com/sync?method=aliexpress.affiliate.product.query&${params.toString()}`
    );
    if (!r.ok) return null;
    const data = await r.json();
    return data.aliexpress_affiliate_product_query_response?.resp_result?.result?.products?.product || null;
  } catch {
    return null;
  }
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
  if (!r.ok) throw new Error(await r.text());
  return r.headers.get('X-RestLi-Id');
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const daySlot = dayOfWeek === 2 ? 0 : 1;
  const kwIdx = (weekNum * 2 + daySlot) % PRODUCT_KEYWORDS.length;
  const kw = PRODUCT_KEYWORDS[kwIdx];

  const results = [];
  const products = [];

  // Amazon
  const amazonItems = await searchAmazonProducts(kw.keyword);
  if (amazonItems && amazonItems.length > 0) {
    for (const item of amazonItems.slice(0, 2)) {
      const price = item.Offers?.Listings?.[0]?.Price?.DisplayAmount || '?';
      products.push({
        platform: 'amazon',
        title: item.ItemInfo?.Title?.DisplayValue?.substring(0, 80) || kw.keyword,
        price,
        url: item.DetailPageURL,
        image: item.Images?.Primary?.Medium?.URL,
      });
    }
  } else {
    // Direkt Affiliate Suchlink wenn keine PA API
    const searchUrl = await getAmazonDirectLink(kw.keyword);
    products.push({ platform: 'amazon', title: kw.keyword, price: null, url: searchUrl });
  }

  // eBay
  const ebayItems = await searchEbayProducts(kw.keyword);
  if (ebayItems && ebayItems.length > 0) {
    for (const item of ebayItems.slice(0, 2)) {
      products.push({
        platform: 'ebay',
        title: item.title?.substring(0, 80) || kw.keyword,
        price: item.price?.value ? `€${item.price.value}` : '?',
        url: getEbayAffiliateLink(item.itemId),
      });
    }
  } else if (EBAY_CAMPAIGN_ID) {
    products.push({
      platform: 'ebay',
      title: kw.keyword,
      url: `https://rover.ebay.com/rover/1/707-53477-19255-0/1?icep_id=114&ipn=icep&toolid=20004&campid=${EBAY_CAMPAIGN_ID}&mpre=https://www.ebay.de/sch/i.html?_nkw=${encodeURIComponent(kw.keyword)}&customid=${EBAY_AFFILIATE_CUSTOM_ID}`,
    });
  }

  // AliExpress
  const aliItems = await searchAliExpressProducts(kw.keyword);
  if (aliItems && aliItems.length > 0) {
    for (const item of aliItems.slice(0, 2)) {
      products.push({
        platform: 'aliexpress',
        title: item.product_title?.substring(0, 80) || kw.keyword,
        price: item.target_sale_price ? `€${item.target_sale_price}` : '?',
        url: item.promotion_link || item.product_detail_url,
        commission: item.commission_rate,
      });
    }
  }

  if (products.length === 0) {
    await sendTelegram(
      `⚠️ <b>Affiliate Produkte — Credentials fehlen!</b>\n\n` +
      `Kategorie: ${kw.keyword}\n\n` +
      `<b>Amazon Setup:</b>\n` +
      `1. programm.amazon.de → Associates anmelden\n` +
      `2. associate-tag: aiitec-21 (schon reserviert)\n` +
      `3. affiliate.amazon.de → PA API Zugang beantragen\n` +
      `4. <code>vercel env add AMAZON_ACCESS_KEY production</code>\n` +
      `5. <code>vercel env add AMAZON_SECRET_KEY production</code>\n\n` +
      `<b>eBay Setup:</b>\n` +
      `1. partnernetwork.ebay.com → Anmelden\n` +
      `2. developer.ebay.com → App ID\n` +
      `3. <code>vercel env add EBAY_APP_ID production</code>\n` +
      `4. <code>vercel env add EBAY_CAMPAIGN_ID production</code>\n\n` +
      `<b>AliExpress Setup:</b>\n` +
      `1. portals.aliexpress.com → Affiliate\n` +
      `2. <code>vercel env add ALIEXPRESS_APP_KEY production</code>\n` +
      `3. <code>vercel env add ALIEXPRESS_ACCESS_TOKEN production</code>`
    );
    return res.status(200).json({ ok: true, products: [], note: 'credentials_missing' });
  }

  // LinkedIn + Telegram Post mit echten Produktdaten
  const productLines = products.map((p) =>
    `• ${p.title}${p.price ? ` — ${p.price}` : ''} [${p.platform.toUpperCase()}]\n  ${p.url}`
  ).join('\n\n');

  const linkedinText = `🛒 Smart Home Deals der Woche — ${kw.keyword}

Aktuelle Top-Angebote aus Amazon DE + eBay + AliExpress:

${productLines}

💡 Diese Produkte sind Affiliate-Links — ich erhalte eine kleine Provision bei Kauf, ohne Mehrkosten für dich.

Für vollständige Automatisierung meines Online-Business: autoincome-ai.vercel.app

#SmartHome #Gadgets #Amazon #Deals #AffiliateMarketing #OnlineBusiness`;

  try {
    const postId = await postLinkedIn(linkedinText);
    await sendTelegram(`✅ LinkedIn Affiliate Post live!\n${products.length} Produkte: ${kw.keyword}\nPost ID: ${postId}`);
    results.push({ platform: 'linkedin', postId, products: products.length });
  } catch (err) {
    await sendTelegram(`⚠️ LinkedIn Fehler: ${err.message.substring(0, 100)}\n\n${productLines.substring(0, 300)}`);
  }

  await sendTelegram(`🛒 <b>Affiliate Deals (${kw.keyword}):</b>\n\n${productLines.substring(0, 600)}`);
  results.push({ products });

  return res.status(200).json({ ok: true, keyword: kw.keyword, results });
}
