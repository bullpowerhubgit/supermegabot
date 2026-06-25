// Weekly SEO Article Generator — FULLY AUTONOMOUS
// Runs every Sunday 06:00 UTC via Vercel Cron
// Generates German KI-Einkommen article with OpenAI gpt-4o-mini
// Saves to Supabase seo_content table (published=true)
// Article served dynamically at /blog/:slug via api/blog.js
// Submits to IndexNow for fast Google/Bing indexing
// Sends Telegram notification

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const PERPLEXITY_KEY = process.env.PERPLEXITY_API_KEY;
const GEMINI_KEY = process.env.GOOGLE_API_KEY || process.env.GCP_API_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';
const SITE_HOST = 'autoincome-ai.vercel.app';
const INDEXNOW_KEY = 'bullpower2026indexnow';

// 52 rotating topics (one per week = 1 year cycle) — all unique, not in existing 100 articles
const ARTICLE_TOPICS = [
  { keyword: 'KI Video erstellen Geld verdienen', slug: 'ki-video-erstellen-geld-verdienen', title: 'Mit KI Videos erstellen und Geld verdienen 2026 — Komplette Anleitung', desc: 'Wie du mit KI-Tools wie Synthesia und HeyGen Videos erstellst und auf YouTube und TikTok monetarisierst.' },
  { keyword: 'Pinterest Shop erstellen', slug: 'pinterest-shop-2026-aufbauen', title: 'Pinterest Shop erstellen 2026 — Passives Einkommen mit Product Pins', desc: 'Wie du einen Pinterest Shop aufbaust, Produkte verlinkst und automatisch Traffic und Sales generierst.' },
  { keyword: 'Fiverr Gig erstellen', slug: 'fiverr-gig-erstellen-anleitung', title: 'Fiverr Gig erstellen 2026 — So bekommst du die ersten Aufträge', desc: 'Schritt-für-Schritt: Wie du deinen ersten Fiverr Gig erstellst, optimierst und in die Top-Suchergebnisse kommst.' },
  { keyword: 'Upwork Profil optimieren', slug: 'upwork-profil-optimieren-2026', title: 'Upwork Profil optimieren 2026 — Mehr Aufträge als Freelancer', desc: 'Wie du dein Upwork-Profil für maximale Sichtbarkeit optimierst — Titel, Beschreibung, Portfolio, Preis.' },
  { keyword: 'Funnel erstellen kostenlos', slug: 'sales-funnel-erstellen-kostenlos', title: 'Sales Funnel kostenlos erstellen 2026 — Von Lead zu Käufer', desc: 'Wie du einen funktionierenden Sales Funnel ohne Budget baust — Landing Page, Lead Magnet, E-Mail, Sale.' },
  { keyword: 'Landing Page erstellen', slug: 'landing-page-erstellen-geld-2026', title: 'Landing Page erstellen 2026 — Die Elemente die wirklich konvertieren', desc: 'Wie du eine Landing Page aufbaust die Besucher zu Käufern macht — kostenlos, ohne Programmierkenntnisse.' },
  { keyword: 'SEO Anfänger Guide', slug: 'seo-anleitung-anfaenger-2026', title: 'SEO Anleitung für Anfänger 2026 — Mehr Google-Traffic ohne Budget', desc: 'SEO-Grundlagen auf Deutsch: Wie du Inhalte erstellst die Google rankt und dauerhaft Traffic bringen.' },
  { keyword: 'Keyword Recherche kostenlos', slug: 'keyword-recherche-kostenlos-2026', title: 'Keyword Recherche kostenlos 2026 — Die besten Gratis-Tools', desc: 'Welche kostenlosen Tools für Keyword-Recherche wirklich funktionieren und wie du profitable Keywords findest.' },
  { keyword: 'YouTube SEO 2026', slug: 'youtube-seo-mehr-views-2026', title: 'YouTube SEO 2026 — Mehr Views ohne bezahlte Werbung', desc: 'Wie du deine YouTube-Videos für maximale organische Reichweite optimierst — Titel, Tags, Thumbnail, Beschreibung.' },
  { keyword: 'Ghostwriter KI werden', slug: 'ghostwriter-ki-werden-2026', title: 'Als KI-Ghostwriter Geld verdienen 2026 — Tagessatz und Einstieg', desc: 'Wie du als Ghostwriter mit KI-Unterstützung E-Books, Artikel und Skripte schreibst und €500–€5000 pro Projekt verdienst.' },
  { keyword: 'Print on Demand Nischen', slug: 'print-on-demand-nischen-2026', title: 'Beste Print on Demand Nischen 2026 — Was sich wirklich verkauft', desc: 'Welche Nischen im Print on Demand 2026 profitabel sind — und welche du meiden solltest.' },
  { keyword: 'Printify Shopify verbinden', slug: 'printify-shopify-anleitung-2026', title: 'Printify mit Shopify verbinden 2026 — Setup in 30 Minuten', desc: 'Schritt-für-Schritt: Wie du Printify mit Shopify verbindest und deinen ersten Print-on-Demand-Artikel live stellst.' },
  { keyword: 'Etsy Alternative digitale Produkte', slug: 'etsy-alternativen-2026', title: 'Etsy Alternativen 2026 — Bessere Plattformen für digitale Produkte', desc: 'Die besten Etsy-Alternativen 2026: Gumroad, Digistore24, Creative Market — Vergleich der Gebühren und Reichweite.' },
  { keyword: 'KI Texte für Amazon', slug: 'ki-texte-amazon-listing-2026', title: 'KI für Amazon Listings 2026 — Bessere Produkttexte in Minuten', desc: 'Wie du mit KI-Tools Amazon-Produktbeschreibungen, Titel und Bullet Points optimierst — mehr Klicks, mehr Sales.' },
  { keyword: 'digitaler Nomade werden 2026', slug: 'digitaler-nomade-werden-2026', title: 'Digitaler Nomade werden 2026 — Was du wirklich brauchst', desc: 'Die ehrliche Antwort: Was ein digitaler Nomade wirklich verdient, welche Jobs funktionieren und was scheitert.' },
  { keyword: 'Produktfotografie KI', slug: 'produktfotografie-ki-2026', title: 'Produktfotos mit KI erstellen 2026 — Profi-Look ohne Fotostudio', desc: 'Wie du mit KI-Tools professionelle Produktfotos für Amazon, Etsy und Shopify erstellst — ohne Kamera, ohne Studio.' },
  { keyword: 'ChatGPT Shopify Beschreibungen', slug: 'chatgpt-shopify-beschreibungen', title: 'ChatGPT für Shopify Produktbeschreibungen 2026 — Mehr Conversion', desc: 'Wie du ChatGPT für SEO-optimierte Shopify-Produkttexte nutzt, die Kunden überzeugen und Google-Rankings steigern.' },
  { keyword: 'Membership Site aufbauen', slug: 'membership-site-aufbauen-2026', title: 'Membership Site aufbauen 2026 — Monatlich wiederkehrende Einnahmen', desc: 'Wie du eine Mitglieder-Website oder Community erstellst, die monatlich wiederkehrendes Einkommen generiert.' },
  { keyword: 'Copywriting lernen online', slug: 'copywriting-lernen-online-2026', title: 'Copywriting lernen 2026 — Von Null zum bezahlten Texter', desc: 'Wie du Copywriting lernst, erste Kunden findest und als Texter €500–€3.000 pro Monat verdienst.' },
  { keyword: 'Amazon KDP Buch veröffentlichen', slug: 'amazon-kdp-buch-veroeffentlichen-2026', title: 'Amazon KDP 2026 — Buch veröffentlichen und passiv verdienen', desc: 'Wie du ein Buch über Amazon Kindle Direct Publishing veröffentlichst — Schreibprozess, Cover, Preis, Marketing.' },
  { keyword: 'Dropshipping Lieferant finden', slug: 'dropshipping-lieferant-finden-2026', title: 'Dropshipping Lieferanten finden 2026 — EU-Lieferanten vs AliExpress', desc: 'Wo du zuverlässige Dropshipping-Lieferanten in der EU und weltweit findest — Vergleich Plattformen und Kriterien.' },
  { keyword: 'Online Coaching Business', slug: 'online-coaching-business-aufbauen', title: 'Online Coaching Business aufbauen 2026 — Von 0 auf erste Kunden', desc: 'Wie du als Coach online Kunden gewinnst, Pakete strukturierst und €1.000–€10.000 pro Monat verdienst.' },
  { keyword: 'Podcast Affiliate Marketing', slug: 'podcast-affiliate-marketing-2026', title: 'Podcast + Affiliate Marketing 2026 — Die perfekte Kombination', desc: 'Wie du deinen Podcast mit Affiliate Marketing verbindest und passives Einkommen durch Empfehlungen aufbaust.' },
  { keyword: 'Newsletter monetarisieren', slug: 'newsletter-monetarisieren-strategien', title: 'Newsletter monetarisieren 2026 — 6 Wege die wirklich Geld bringen', desc: 'Paid Subscriptions, Affiliate Links, Sponsoren, eigene Produkte — welche Newsletter-Monetarisierung sich lohnt.' },
  { keyword: 'Etsy Shop erfolgreich machen', slug: 'etsy-shop-tipps-2026', title: 'Etsy Shop Tipps 2026 — Was Top-Verkäufer anders machen', desc: 'Die wichtigsten Faktoren für einen erfolgreichen Etsy Shop — Nische, Titel, Tags, Fotos, Preisgestaltung.' },
  { keyword: 'KI Stimme Geld verdienen', slug: 'ki-stimme-geld-verdienen-2026', title: 'Mit KI-Stimme Geld verdienen 2026 — Voiceover und Hörbücher', desc: 'Wie du mit KI-generierten Stimmen Voiceovers, Hörbücher und Podcast-Intros erstellst und verkaufst.' },
  { keyword: 'KI Musiker werden', slug: 'ki-musik-erstellen-verkaufen-2026', title: 'KI Musik erstellen und verkaufen 2026 — Lizenzfreie Songs generieren', desc: 'Wie du mit KI-Tools Musik erstellst, Lizenzrechte klärst und auf Stockmusik-Plattformen passive Einnahmen erzielst.' },
  { keyword: 'Shopify eigene Marke aufbauen', slug: 'shopify-eigene-marke-aufbauen', title: 'Eigene Marke auf Shopify aufbauen 2026 — Private Label statt Dropshipping', desc: 'Warum Private Label langfristig profitabler als Dropshipping ist und wie du mit kleinem Budget startest.' },
  { keyword: 'Google Ads Grundlagen', slug: 'google-ads-grundlagen-einsteiger', title: 'Google Ads für Einsteiger 2026 — Erste Kampagne ohne Budget-Burnout', desc: 'Wie du deine erste Google Ads Kampagne so aufsetzt, dass du nicht unnötig Geld verbrennst.' },
  { keyword: 'Facebook Gruppe monetarisieren', slug: 'facebook-gruppe-monetarisieren-2026', title: 'Facebook Gruppe monetarisieren 2026 — Community als Einkommensquelle', desc: 'Wie du eine Facebook-Gruppe von 500–5.000 Mitgliedern zu einer profitablen Einkommensquelle machst.' },
  { keyword: 'KI Daten Analyse Freelancer', slug: 'ki-datenanalyse-freelancer-2026', title: 'KI Datenanalyse als Freelancer 2026 — Ein lukratives Nischenmodell', desc: 'Wie du mit KI-Tools Datenanalyse als Dienstleistung anbietest und €50–€150 pro Stunde verdienst.' },
  { keyword: 'Backlinks aufbauen kostenlos', slug: 'backlinks-aufbauen-kostenlos-2026', title: 'Backlinks aufbauen kostenlos 2026 — White Hat Methoden die funktionieren', desc: 'Wie du hochwertige Backlinks für deine Website bekommst — ohne Geld auszugeben, ohne Risiko.' },
  { keyword: 'Online Shop Marketing', slug: 'online-shop-marketing-strategien-2026', title: 'Online Shop Marketing 2026 — Die effektivsten Kanäle ohne Budget', desc: 'Welche Marketing-Strategien für kleine Online-Shops 2026 wirklich Traffic und Sales bringen — praxisorientiert.' },
  { keyword: 'Preisgestaltung digitale Produkte', slug: 'preisgestaltung-digitale-produkte-2026', title: 'Digitale Produkte richtig bepreisen 2026 — Die Psychologie dahinter', desc: 'Wie du den optimalen Preis für E-Books, Kurse und Templates findest — Psychologie, Markt und Strategie.' },
  { keyword: 'Lead Magnet erstellen', slug: 'lead-magnet-erstellen-ideen-2026', title: 'Lead Magnet erstellen 2026 — Was wirklich E-Mails sammelt', desc: 'Die besten Lead-Magnet-Ideen 2026: Was Besucher wirklich motiviert, ihre E-Mail-Adresse einzutragen.' },
  { keyword: 'Testimonials und Bewertungen online', slug: 'testimonials-bewertungen-aufbauen-2026', title: 'Testimonials aufbauen 2026 — Vertrauen ohne viele Kunden', desc: 'Wie du als Anfänger Testimonials und soziale Beweise sammelst, die neue Kunden überzeugen.' },
  { keyword: 'KI Buchzusammenfassung Geld', slug: 'ki-buchzusammenfassungen-verdienen-2026', title: 'Mit Buchzusammenfassungen Geld verdienen 2026 — KI macht es einfach', desc: 'Wie du mit KI Buchzusammenfassungen für YouTube, Newsletter oder E-Books erstellst und monetarisierst.' },
  { keyword: 'Produktlaunch Strategie', slug: 'produktlaunch-strategie-digital-2026', title: 'Digitalen Produktlaunch planen 2026 — Von Null auf erste Verkäufe in 7 Tagen', desc: 'Wie du ein digitales Produkt lancierst — Pre-Launch, Launch-Tag, Post-Launch und Fehler die du vermeiden sollst.' },
  { keyword: 'Nischen finden Online Business', slug: 'nische-finden-online-business-2026', title: 'Profitable Nische finden 2026 — So wählst du das richtige Thema', desc: 'Wie du eine profitable Nische für dein Online Business findest — mit konkreten Tools, Kriterien und Beispielen.' },
  { keyword: 'Steuer Online Business Österreich', slug: 'steuer-online-business-oesterreich', title: 'Steuern für Online Business in Österreich 2026 — Was du beachten musst', desc: 'Gewerbesteuer, Einkommensteuer, USt — wie Online-Business-Inhaber in Österreich legal und effizient abrechnen.' },
  { keyword: 'Schweiz Online Business Geld', slug: 'online-business-schweiz-2026', title: 'Online Business in der Schweiz aufbauen 2026 — Steuern, Plattformen, Chancen', desc: 'Besonderheiten für Online-Business-Inhaber in der Schweiz: Mehrwertsteuer, CHF vs EUR, beste Plattformen.' },
  { keyword: 'KI Übersetzer Geld verdienen', slug: 'ki-uebersetzer-geld-verdienen-2026', title: 'Als KI-Übersetzer Geld verdienen 2026 — Nische mit wachsender Nachfrage', desc: 'Wie du KI-Übersetzungstools nutzt um mehr Projekte in weniger Zeit zu liefern und als Übersetzer zu skalieren.' },
  { keyword: 'Live Selling Social Media', slug: 'live-selling-social-media-2026', title: 'Live Selling 2026 — Produkte live verkaufen auf TikTok und Instagram', desc: 'Wie du Live-Shopping-Sessions auf TikTok und Instagram nutzt um Produkte direkt zu verkaufen.' },
  { keyword: 'UGC Content Creator werden', slug: 'ugc-content-creator-werden-2026', title: 'UGC Content Creator werden 2026 — Marken zahlen bis €500 pro Video', desc: 'Was User Generated Content ist, wie Marken UGC-Creators bezahlen und wie du in 30 Tagen erste Aufträge bekommst.' },
  { keyword: 'Reselling Business starten', slug: 'reselling-business-starten-2026', title: 'Reselling Business starten 2026 — Produkte kaufen und teurer verkaufen', desc: 'Wie du mit Reselling (eBay Flipping, Amazon Reselling) ein skalierbares Nebengeschäft aufbaust.' },
  { keyword: 'KI Chatbot Geld verdienen', slug: 'ki-chatbot-geld-verdienen-2026', title: 'KI Chatbot entwickeln und verkaufen 2026 — Lukratives B2B-Modell', desc: 'Wie du KI-Chatbots ohne Programmierkenntnisse für Unternehmen baust und €500–€5.000 pro Chatbot verdienst.' },
  { keyword: 'Online Kurs Ideen 2026', slug: 'online-kurs-ideen-2026', title: 'Online Kurs Ideen 2026 — Was sich gut verkauft', desc: 'Die gefragtesten Online-Kurs-Themen 2026: Welche Nischen boomen, was Käufer zahlen und wie du startest.' },
  { keyword: 'KI Assistenten Geld sparen', slug: 'ki-assistenten-geld-sparen-2026', title: 'Mit KI-Assistenten Geld sparen und verdienen 2026 — Die besten Hacks', desc: 'Wie KI-Assistenten nicht nur Zeit, sondern auch Geld sparen — und wie du das zur Einkommensquelle machst.' },
  { keyword: 'Influencer Marketing ohne große Follower', slug: 'influencer-marketing-micro-2026', title: 'Influencer Marketing 2026 — Auch als Micro-Influencer gut verdienen', desc: 'Wie Micro-Influencer mit 500–5.000 Followern mehr pro Post verdienen als manche mit 100.000 Followern.' },
  { keyword: 'Digitale Rechnung erstellen', slug: 'digitale-rechnung-online-business-2026', title: 'Rechnungen für Online Business 2026 — Pflichtangaben und Tools', desc: 'Welche Pflichtangaben eine Rechnung im Online Business haben muss und welche kostenlosen Tools das automatisieren.' },
  { keyword: 'KI Unterricht und Nachhilfe', slug: 'ki-nachhilfe-online-geld-2026', title: 'Online Nachhilfe mit KI 2026 — Passives Einkommen als Tutor', desc: 'Wie du Online-Nachhilfe oder Lernkurse mit KI-Unterstützung erstellst und auf Plattformen oder eigener Site verkaufst.' },
  { keyword: 'Nischen Blog aufbauen Geld', slug: 'nischen-blog-aufbauen-geld-2026', title: 'Nischen-Blog aufbauen 2026 — Von 0 auf erste Einnahmen in 90 Tagen', desc: 'Wie du einen profitablen Nischen-Blog in 90 Tagen aufbaust — Nischenwahl, Content-Plan, Monetarisierung.' },
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

async function generateArticle(topic) {
  const prompt = `Schreibe einen detaillierten deutschen SEO-Artikel zum Thema "${topic.keyword}".

Anforderungen:
- 1000-1400 Wörter
- Auf Deutsch, Zielgruppe: Anfänger die online Geld verdienen wollen
- Keyword "${topic.keyword}" natürlich in H1, erste H2 und Text einbauen
- Ehrlich, hilfreich, KEINE übertriebenen Versprechen
- Konkrete Zahlen, Tools, Schritte wo möglich
- Am Ende ein kurzer CTA-Absatz zum AI Income Machine Blueprint (${PRODUCT_URL})
- Format: Fließtext mit ## für H2 und ### für H3, **fett** für wichtige Begriffe
- Keine HTML-Tags, nur Markdown

Beginne direkt mit dem ersten Absatz (kein Titel, keine Einleitung).`;

  // Gemini (Google AI — kostenlos) bevorzugt, Perplexity als Fallback
  if (GEMINI_KEY) {
    const r = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${GEMINI_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { maxOutputTokens: 2200, temperature: 0.7 },
        }),
      }
    );
    if (r.ok) {
      const data = await r.json();
      const content = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (content) {
        return { content, wordCount: content.split(/\s+/).length };
      }
    }
  }

  if (!PERPLEXITY_KEY) throw new Error('Kein API Key (Gemini + Perplexity beide nicht verfügbar)');

  const r = await fetch('https://api.perplexity.ai/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${PERPLEXITY_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'sonar',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 2200,
      temperature: 0.7,
    }),
  });
  if (!r.ok) throw new Error(`Perplexity ${r.status}: ${await r.text().then((t) => t.substring(0, 200))}`);
  const data = await r.json();
  const content = data.choices[0].message.content;
  return { content, wordCount: content.split(/\s+/).length };
}

function markdownToHtml(md) {
  return md
    .replace(/^## (.+)$/gm, '</p><h2>$1</h2><p>')
    .replace(/^### (.+)$/gm, '</p><h3>$1</h3><p>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
    .replace(/<p><\/p>/g, '');
}

async function saveToSupabase(topic, contentHtml, wordCount, dateStr) {
  const schemaJson = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: topic.title,
    description: topic.desc,
    author: { '@type': 'Person', name: 'Rudolf Sarkany' },
    publisher: { '@type': 'Organization', name: 'AiiteC' },
    datePublished: dateStr,
    url: `https://${SITE_HOST}/blog/${topic.slug}`,
  };

  const payload = {
    keyword: topic.keyword,
    title: topic.title,
    slug: topic.slug,
    meta_description: topic.desc,
    content_html: contentHtml,
    schema_json: schemaJson,
    language: 'de',
    word_count: wordCount,
    published: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  // Upsert (insert or update by slug)
  const r = await fetch(`${SUPABASE_URL}/rest/v1/seo_content`, {
    method: 'POST',
    headers: {
      apikey: SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_KEY}`,
      'Content-Type': 'application/json',
      Prefer: 'resolution=merge-duplicates,return=minimal',
    },
    body: JSON.stringify(payload),
  });
  if (!r.ok && r.status !== 409) {
    const err = await r.text();
    throw new Error(`Supabase save failed ${r.status}: ${err.substring(0, 200)}`);
  }
  return true;
}

async function submitToIndexNow(slug) {
  try {
    await fetch('https://api.indexnow.org/IndexNow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        host: SITE_HOST,
        key: INDEXNOW_KEY,
        keyLocation: `https://${SITE_HOST}/${INDEXNOW_KEY}.txt`,
        urlList: [`https://${SITE_HOST}/blog/${slug}`],
      }),
    });
  } catch {}
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  // Rotate by week number
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));

  if (!PERPLEXITY_KEY) {
    // No API key — re-ping IndexNow for existing articles to keep Google crawling
    const existingUrls = ARTICLE_TOPICS.map((t) => `https://${SITE_HOST}/blog/${t.slug}`);
    await submitToIndexNow(existingUrls[weekNum % existingUrls.length].split('/blog/')[1]);
    await sendTelegram('ℹ️ SEO Writer: kein API-Key — IndexNow-Ping für bestehende Artikel gesendet.');
    return res.status(200).json({ ok: true, note: 'no api key, indexnow ping sent' });
  }
  if (!SUPABASE_SERVICE_KEY) {
    await sendTelegram('❌ SEO Writer: SUPABASE_SERVICE_KEY fehlt!');
    return res.status(500).json({ error: 'SUPABASE_SERVICE_KEY missing' });
  }
  const topic = ARTICLE_TOPICS[weekNum % ARTICLE_TOPICS.length];
  const dateStr = new Date().toISOString().split('T')[0];
  const pageUrl = `https://${SITE_HOST}/blog/${topic.slug}`;

  // Generate
  let content, wordCount;
  try {
    ({ content, wordCount } = await generateArticle(topic));
  } catch (err) {
    await sendTelegram(`❌ SEO Writer Perplexity Fehler: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }

  const contentHtml = markdownToHtml(content);

  // Save to Supabase
  try {
    await saveToSupabase(topic, contentHtml, wordCount, dateStr);
  } catch (err) {
    await sendTelegram(`❌ SEO Writer Supabase Fehler: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }

  // Submit to IndexNow
  await submitToIndexNow(topic.slug);

  await sendTelegram(
    `✍️ <b>SEO Artikel veröffentlicht!</b>\n\n📝 <b>${topic.title}</b>\n🔑 ${topic.keyword}\n📊 ${wordCount} Wörter\n🔗 ${pageUrl}\n\nArtikel ist sofort live via /blog/${topic.slug}`
  );

  return res.status(200).json({
    ok: true,
    slug: topic.slug,
    title: topic.title,
    wordCount,
    pageUrl,
  });
}
