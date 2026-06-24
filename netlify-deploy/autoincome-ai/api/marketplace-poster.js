// Marketplace Automation: Gumroad + Etsy + Fiverr/Upwork
// Gumroad/Etsy: Mi/Sa 15:00 UTC — Produkte + Coupons
// Fiverr/Upwork: täglich 08:00 UTC — Gig-Erinnerungen + Job-Tipps
// Benötigt: GUMROAD_ACCESS_TOKEN, ETSY_API_KEY, ETSY_ACCESS_TOKEN, ETSY_SHOP_ID

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const GUMROAD_TOKEN = process.env.GUMROAD_ACCESS_TOKEN;
const ETSY_KEY = process.env.ETSY_API_KEY;
const ETSY_TOKEN = process.env.ETSY_ACCESS_TOKEN;
const ETSY_SHOP_ID = process.env.ETSY_SHOP_ID;
const PRODUCT_URL_37 = 'https://www.checkout-ds24.com/product/668035';
const PRODUCT_URL_97 = 'https://www.checkout-ds24.com/product/704677';

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
  if (secret !== process.env.CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });

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

    // Etsy
    if (ETSY_KEY && ETSY_TOKEN && ETSY_SHOP_ID) {
      try {
        for (const listing of ETSY_LISTINGS) {
          const created = await etsyCreateListing(listing);
          await sendTelegram(`✅ Etsy Listing erstellt!\n📦 ID: ${created.listing_id}\n📝 ${listing.title}`);
          results.push({ platform: 'etsy', listingId: created.listing_id });
        }
      } catch (err) {
        await sendTelegram(`⚠️ Etsy Fehler: ${err.message.substring(0, 150)}`);
        results.push({ platform: 'etsy', error: err.message });
      }
    } else {
      await sendTelegram(
        `🛍️ <b>Etsy Setup:</b>\n` +
        `1. etsy.com → Shop erstellen\n` +
        `2. developers.etsy.com → App erstellen\n` +
        `3. OAuth2 Token (scope: listings_w)\n` +
        `4. <code>vercel env add ETSY_API_KEY production</code>\n` +
        `5. <code>vercel env add ETSY_ACCESS_TOKEN production</code>\n` +
        `6. <code>vercel env add ETSY_SHOP_ID production</code>\n\n` +
        `Etsy: 90 Mio. Käufer, digitale Downloads sofort geliefert!`
      );
    }
  }

  return res.status(200).json({ ok: true, results, day: dayOfWeek });
}
