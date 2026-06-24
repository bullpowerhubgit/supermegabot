// Weekly SEO Article Generator — FULLY AUTONOMOUS
// Runs every Sunday 06:00 UTC via Vercel Cron
// Generates German KI-Einkommen article with OpenAI gpt-4o-mini
// Saves to Supabase seo_content table (published=true)
// Article served dynamically at /blog/:slug via api/blog.js
// Submits to IndexNow for fast Google/Bing indexing
// Sends Telegram notification

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const OPENAI_KEY = process.env.OPENAI_API_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';
const SITE_HOST = 'autoincome-ai.vercel.app';
const INDEXNOW_KEY = 'bullpower2026indexnow';

// 12 rotating article topics (one per week, repeats quarterly)
const ARTICLE_TOPICS = [
  { keyword: 'ChatGPT E-Book erstellen', slug: 'chatgpt-ebook-erstellen', title: 'ChatGPT E-Book erstellen und verkaufen 2026 — Schritt-für-Schritt Anleitung', desc: 'Wie du mit ChatGPT in 2-4 Stunden ein E-Book erstellst und auf Digistore24 für €27-€97 verkaufst.' },
  { keyword: 'Digistore24 Anfänger', slug: 'digistore24-anfaenger-guide', title: 'Digistore24 für Anfänger 2026 — Von Registrierung bis erstem Verkauf', desc: 'Der vollständige Guide: wie du auf Digistore24 dein erstes Produkt verkaufst — mit realen Zahlen.' },
  { keyword: 'passives Einkommen aufbauen', slug: 'passives-einkommen-aufbauen-2026', title: 'Passives Einkommen aufbauen 2026 — 5 realistische Strategien', desc: 'Welche passiven Einkommensquellen wirklich funktionieren und was nur gut klingt — ehrlicher Vergleich.' },
  { keyword: 'KI Tools kostenlos Geld verdienen', slug: 'ki-tools-kostenlos-geld-verdienen', title: 'Mit kostenlosen KI-Tools Geld verdienen 2026 — die besten Gratis-Methoden', desc: 'Diese 7 kostenlosen KI-Tools reichen aus um ein digitales Produkt zu erstellen und zu verkaufen.' },
  { keyword: 'Affiliate Marketing Anfänger Deutschland', slug: 'affiliate-marketing-anfaenger-deutschland', title: 'Affiliate Marketing für Anfänger in Deutschland 2026 — Ehrlicher Leitfaden', desc: 'Was Affiliate Marketing wirklich ist, wie lange es dauert und welche Plattformen sich in Deutschland lohnen.' },
  { keyword: 'Online Business Deutschland starten', slug: 'online-business-deutschland-starten', title: 'Online Business in Deutschland starten 2026 — Rechtliches und erste Einnahmen', desc: 'Wie du legal ein Online-Business aufbaust — Gewerbeanmeldung, Steuern, Plattformwahl, erste Kunden.' },
  { keyword: 'LinkedIn Follower aufbauen Business', slug: 'linkedin-follower-business-aufbauen', title: 'LinkedIn Follower für dein Business aufbauen 2026 — 0 auf 1000 in 90 Tagen', desc: 'Wie du auf LinkedIn organisch Follower gewinnst und direkt Produkte und Dienstleistungen verkaufst.' },
  { keyword: 'E-Mail Marketing Klaviyo kostenlos', slug: 'email-marketing-klaviyo-kostenlos', title: 'E-Mail Marketing mit Klaviyo kostenlos 2026 — von 0 auf erste Conversions', desc: 'Wie du mit Klaviyo Free bis 250 Subscriber eine automatische Sequenz aufbaust die für dich verkauft.' },
  { keyword: 'KI Automatisierung Einkommen', slug: 'ki-automatisierung-einkommen-aufbauen', title: 'KI Automatisierung für passives Einkommen 2026 — konkrete Systeme die laufen', desc: 'Welche Automatisierungen echtes Einkommen generieren — mit Stack, Tools und realistischen Zeitplänen.' },
  { keyword: 'digitale Produkte verkaufen Deutschland', slug: 'digitale-produkte-verkaufen-deutschland', title: 'Digitale Produkte verkaufen in Deutschland 2026 — Plattformen und Erfahrungen', desc: 'Welche Plattformen sich lohnen, was steuerlich zu beachten ist und wie dein erstes Produkt entsteht.' },
  { keyword: 'ChatGPT Online Business aufbauen', slug: 'chatgpt-online-business-aufbauen', title: 'Online Business mit ChatGPT aufbauen 2026 — 5 Geschäftsmodelle im Vergleich', desc: 'Diese 5 Online-Business-Modelle lassen sich mit ChatGPT realisieren — mit realistischen Einkommenserwartungen.' },
  { keyword: 'KI Freelancer werden Deutschland', slug: 'ki-freelancer-werden-deutschland', title: 'Als KI-Freelancer starten 2026 — wie Quereinsteiger sofort Aufträge bekommen', desc: 'Wie du KI-Tools nutzt um als Freelancer mehr Projekte in weniger Zeit zu liefern — und was Kunden wirklich zahlen.' },
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

  const r = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${OPENAI_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 2200,
      temperature: 0.7,
    }),
  });
  if (!r.ok) throw new Error(`OpenAI ${r.status}: ${await r.text().then((t) => t.substring(0, 200))}`);
  const data = await r.json();
  const content = data.choices[0].message.content;
  const wordCount = content.split(/\s+/).length;
  return { content, wordCount };
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

  if (!OPENAI_KEY) {
    await sendTelegram('❌ SEO Writer: OPENAI_API_KEY fehlt!');
    return res.status(500).json({ error: 'OPENAI_API_KEY missing' });
  }
  if (!SUPABASE_SERVICE_KEY) {
    await sendTelegram('❌ SEO Writer: SUPABASE_SERVICE_KEY fehlt!');
    return res.status(500).json({ error: 'SUPABASE_SERVICE_KEY missing' });
  }

  // Rotate by week number
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const topic = ARTICLE_TOPICS[weekNum % ARTICLE_TOPICS.length];
  const dateStr = new Date().toISOString().split('T')[0];
  const pageUrl = `https://${SITE_HOST}/blog/${topic.slug}`;

  // Generate
  let content, wordCount;
  try {
    ({ content, wordCount } = await generateArticle(topic));
  } catch (err) {
    await sendTelegram(`❌ SEO Writer OpenAI Fehler: ${err.message.substring(0, 200)}`);
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
