// Gumroad + Etsy Automation
// Cron: Mi/Sa 15:00 UTC
// Gumroad: Produkt-Updates + Coupons via API
// Etsy: Neue Listings erstellen + Shop Update via API
// Benötigt: GUMROAD_ACCESS_TOKEN, ETSY_API_KEY + ETSY_ACCESS_TOKEN + ETSY_SHOP_ID

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const GUMROAD_TOKEN = process.env.GUMROAD_ACCESS_TOKEN;
const ETSY_KEY = process.env.ETSY_API_KEY;
const ETSY_TOKEN = process.env.ETSY_ACCESS_TOKEN;
const ETSY_SHOP_ID = process.env.ETSY_SHOP_ID;

const PRODUCT_URL_37 = 'https://www.checkout-ds24.com/product/668035';
const PRODUCT_URL_97 = 'https://www.checkout-ds24.com/product/704677';

// Gumroad Produkt-Daten (wenn noch nicht erstellt)
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

Für wen: Deutsche Online-Unternehmer, Anfänger, Freelancer die ein zweites Einkommen aufbauen wollen.

60-Tage Geld-zurück-Garantie.`,
    price: 3700,
    currency: 'EUR',
    url_slug: 'ai-income-machine-deutsch',
    tags: ['ki', 'passives-einkommen', 'automation', 'digistore24', 'deutsch'],
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
✅ 1-Click Deploy auf Railway

Für wen: Online-Unternehmer die alles automatisieren wollen.`,
    price: 9700,
    currency: 'EUR',
    url_slug: 'supermegabot-ki-automation',
    tags: ['ki-automation', 'bot', 'linkedin', 'instagram', 'deutsch', 'passives-einkommen'],
  },
];

// Etsy Listings
const ETSY_LISTINGS = [
  {
    title: 'AI Income Machine Blueprint German — Passive Income Automation Guide',
    description: `German language guide for building automated passive income with AI tools.

WHAT YOU GET:
• 90-day action plan (PDF, 47 pages, German)
• Digistore24 seller setup guide
• LinkedIn automation templates
• Email marketing sequence (4 automated emails)
• Digital product checklist

LANGUAGE: German (Deutsch)
FORMAT: Instant digital download (PDF)
GUARANTEE: 60-day money-back guarantee

Perfect for: German-speaking entrepreneurs, freelancers, anyone wanting to build a passive income stream in the DACH market (Germany, Austria, Switzerland).

The German market has 85% LESS competition than English for AI content — this is your advantage.`,
    price: 3700,
    quantity: 999,
    taxonomy_id: 2078,
    tags: ['passive income', 'AI tools', 'German guide', 'automation', 'digital download', 'Digistore24', 'online business', 'make money', 'digital product', 'blueprint'],
    materials: ['digital download', 'PDF'],
    who_made: 'i_did',
    when_made: '2020_2024',
    is_supply: false,
    is_digital: true,
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
    headers: {
      Authorization: `Bearer ${GUMROAD_TOKEN}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: body.toString(),
  });
  const data = await r.json();
  if (!data.success) throw new Error(JSON.stringify(data).substring(0, 200));
  return data.product;
}

async function gumroadCreateCoupon(productId, couponCode, discount) {
  const body = new URLSearchParams({
    offer_code: couponCode,
    amount_off: discount,
    max_purchase_count: '10',
  });
  const r = await fetch(`https://api.gumroad.com/v2/products/${productId}/offer_codes`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${GUMROAD_TOKEN}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: body.toString(),
  });
  const data = await r.json();
  return data.offer_code;
}

async function etsyCreateListing(listing) {
  const r = await fetch(`https://openapi.etsy.com/v3/application/shops/${ETSY_SHOP_ID}/listings`, {
    method: 'POST',
    headers: {
      'x-api-key': ETSY_KEY,
      Authorization: `Bearer ${ETSY_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      ...listing,
      shipping_profile_id: 0,
      return_policy_id: 0,
      listing_type: 'download',
    }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(JSON.stringify(data).substring(0, 200));
  return data;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

  const results = [];

  // === GUMROAD ===
  if (GUMROAD_TOKEN) {
    try {
      const existing = await gumroadListProducts();
      const existingNames = existing.map((p) => p.name);

      for (const prod of GUMROAD_PRODUCTS) {
        if (!existingNames.includes(prod.name)) {
          const created = await gumroadCreateProduct(prod);
          results.push({ platform: 'gumroad', action: 'product_created', name: created.name, id: created.id });
          await sendTelegram(`✅ Gumroad Produkt erstellt: ${created.name}\n🔗 gumroad.com/l/${prod.url_slug}`);

          // Erstelle Launch-Coupon (10% Rabatt für erste Käufer)
          await gumroadCreateCoupon(created.id, 'LAUNCH10', 10);
        } else {
          results.push({ platform: 'gumroad', action: 'product_exists', name: prod.name });
        }
      }

      // Wöchentlicher Coupon (rotierend)
      if (existing.length > 0) {
        const weekCoupon = `WEEK${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`;
        const prod = existing[0];
        await gumroadCreateCoupon(prod.id, weekCoupon, 500); // €5 Rabatt
        await sendTelegram(`🎟️ Gumroad Wochencoupon: ${weekCoupon} (€5 Rabatt) für ${prod.name}`);
        results.push({ platform: 'gumroad', action: 'coupon_created', code: weekCoupon });
      }
    } catch (err) {
      await sendTelegram(`⚠️ Gumroad Fehler: ${err.message.substring(0, 150)}`);
      results.push({ platform: 'gumroad', error: err.message });
    }
  } else {
    await sendTelegram(
      `💰 <b>Gumroad Setup (10 Min):</b>\n\n` +
      `1. gumroad.com/signup → Account erstellen\n` +
      `2. app.gumroad.com/settings/advanced → API-Key\n` +
      `3. <code>vercel env add GUMROAD_ACCESS_TOKEN production</code>\n\n` +
      `Dein AI Income Machine Blueprint kann auf Gumroad ZUSÄTZLICH zu DS24 verkauft werden!\n` +
      `Gumroad hat 3 Mio. Käufer weltweit.`
    );
    results.push({ platform: 'gumroad', error: 'GUMROAD_ACCESS_TOKEN not set' });
  }

  // === ETSY ===
  if (ETSY_KEY && ETSY_TOKEN && ETSY_SHOP_ID) {
    try {
      for (const listing of ETSY_LISTINGS) {
        const created = await etsyCreateListing(listing);
        results.push({ platform: 'etsy', action: 'listing_created', id: created.listing_id, title: listing.title });
        await sendTelegram(
          `✅ Etsy Listing erstellt!\n📦 Listing ID: ${created.listing_id}\n📝 ${listing.title}\n` +
          `🔗 etsy.com/listing/${created.listing_id}`
        );
      }
    } catch (err) {
      await sendTelegram(`⚠️ Etsy Fehler: ${err.message.substring(0, 150)}`);
      results.push({ platform: 'etsy', error: err.message });
    }
  } else {
    await sendTelegram(
      `🛍️ <b>Etsy Setup (15 Min):</b>\n\n` +
      `1. etsy.com → Account + Shop erstellen\n` +
      `2. developers.etsy.com → App erstellen (Name: SuperMegaBot)\n` +
      `3. OAuth2 Token holen (scope: listings_w)\n` +
      `4. Shop-ID aus URL: etsy.com/shop/DEIN-SHOP → letzte Ziffer aus API\n\n` +
      `<code>vercel env add ETSY_API_KEY production</code>\n` +
      `<code>vercel env add ETSY_ACCESS_TOKEN production</code>\n` +
      `<code>vercel env add ETSY_SHOP_ID production</code>\n\n` +
      `Etsy hat 90 Mio. aktive Käufer! Digitale Downloads = instant geliefert.`
    );
    results.push({ platform: 'etsy', error: 'Etsy credentials not set' });
  }

  return res.status(200).json({ ok: true, results });
}
