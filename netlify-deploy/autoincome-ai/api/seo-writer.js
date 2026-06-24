// Weekly SEO Article Generator
// Runs every Sunday 06:00 UTC via Vercel Cron
// Uses OpenAI to generate a new German KI-Einkommen article
// Submits to IndexNow for fast Google indexing
// Sends Telegram notification with the new article URL

const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const OPENAI_KEY = process.env.OPENAI_API_KEY;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const AFFILIATE_URL = 'https://autoincome-ai.vercel.app/affiliate.html';
const SITE_HOST = 'autoincome-ai.vercel.app';
const INDEXNOW_KEY = 'bullpower2026indexnow';

// Rotating article topics — 12 topics = one per week for a quarter
const ARTICLE_TOPICS = [
  {
    keyword: 'ChatGPT E-Book erstellen',
    slug: 'chatgpt-ebook-erstellen',
    title: 'ChatGPT E-Book erstellen und verkaufen 2026 — Schritt-für-Schritt Anleitung',
    desc: 'Wie du mit ChatGPT in 2-4 Stunden ein E-Book erstellst und auf Digistore24 für €27-€97 verkaufst.',
  },
  {
    keyword: 'Digistore24 Anfänger Guide',
    slug: 'digistore24-anfaenger-guide',
    title: 'Digistore24 für Anfänger 2026 — Vollständiger Guide zum ersten Verkauf',
    desc: 'Alles was du wissen musst um dein erstes Produkt auf Digistore24 zu verkaufen — von der Registrierung bis zum ersten Geldeingang.',
  },
  {
    keyword: 'passives Einkommen aufbauen',
    slug: 'passives-einkommen-aufbauen',
    title: 'Passives Einkommen aufbauen 2026 — Realistische Strategien die funktionieren',
    desc: 'Ehrlicher Guide: welche passiven Einkommensquellen wirklich funktionieren und was nur gut klingt.',
  },
  {
    keyword: 'KI Tools kostenlos',
    slug: 'ki-tools-kostenlos-geld-verdienen',
    title: 'Mit kostenlosen KI-Tools Geld verdienen — die besten Gratis-Alternativen 2026',
    desc: 'Diese 7 kostenlosen KI-Tools reichen aus um ein digitales Produkt zu erstellen und zu verkaufen.',
  },
  {
    keyword: 'Affiliate Marketing Anfänger',
    slug: 'affiliate-marketing-anfaenger-2026',
    title: 'Affiliate Marketing für Anfänger 2026 — Der ehrliche Leitfaden ohne Hype',
    desc: 'Was Affiliate Marketing wirklich ist, wie lange es dauert bis du verdienst und welche Plattformen sich lohnen.',
  },
  {
    keyword: 'Online Business Deutschland',
    slug: 'online-business-deutschland-starten',
    title: 'Online Business in Deutschland starten 2026 — Rechtliches, Tools und erste Einnahmen',
    desc: 'Wie du legal ein Online-Business in Deutschland aufbaust — Gewerbeanmeldung, Steuern, Plattformen.',
  },
  {
    keyword: 'LinkedIn Follower aufbauen',
    slug: 'linkedin-follower-aufbauen-business',
    title: 'LinkedIn Follower aufbauen für dein Business 2026 — 0 auf 1000 in 90 Tagen',
    desc: 'Wie du auf LinkedIn organisch Follower aufbaust und direkt Produkte verkaufst — ohne bezahlte Werbung.',
  },
  {
    keyword: 'E-Mail Marketing Klaviyo',
    slug: 'email-marketing-klaviyo-anfaenger',
    title: 'E-Mail Marketing mit Klaviyo für Anfänger 2026 — kostenlos bis 250 Subscriber',
    desc: 'Wie du mit Klaviyo Free eine automatische E-Mail-Sequenz aufbaust die für dich verkauft.',
  },
  {
    keyword: 'KI Automatisierung verdienen',
    slug: 'ki-automatisierung-geld-verdienen',
    title: 'Mit KI-Automatisierung Geld verdienen 2026 — konkrete Beispiele und Tools',
    desc: 'Wie KI-Automatisierung echte Einkommensströme erzeugt die ohne dein aktives Zutun laufen.',
  },
  {
    keyword: 'digitale Produkte verkaufen',
    slug: 'digitale-produkte-verkaufen-deutschland',
    title: 'Digitale Produkte verkaufen in Deutschland 2026 — Plattformen, Steuern, Erfahrungen',
    desc: 'Welche Plattformen sich lohnen, was steuerlich zu beachten ist und wie dein erstes Produkt entsteht.',
  },
  {
    keyword: 'ChatGPT Online Business',
    slug: 'chatgpt-online-business-aufbauen',
    title: 'Online Business mit ChatGPT aufbauen 2026 — 5 konkrete Geschäftsmodelle',
    desc: 'Diese 5 Online-Business-Modelle lassen sich mit ChatGPT aufbauen — mit realistischen Einkommenserwartungen.',
  },
  {
    keyword: 'KI Freelancer werden',
    slug: 'ki-freelancer-werden-2026',
    title: 'KI-Freelancer werden 2026 — wie du als Quereinsteiger sofort Aufträge bekommst',
    desc: 'Wie du KI-Tools nutzt um als Freelancer 3-5x mehr Aufträge in der gleichen Zeit zu erledigen.',
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

async function generateArticle(topic) {
  if (!OPENAI_KEY) throw new Error('OPENAI_API_KEY not set');

  const prompt = `Schreibe einen detaillierten deutschen SEO-Artikel zum Thema "${topic.keyword}".

Anforderungen:
- 1000-1500 Wörter
- Auf Deutsch
- Zielgruppe: Deutsche Anfänger die online Geld verdienen wollen
- Keyword "${topic.keyword}" natürlich verwenden
- Ehrlich und hilfreich, KEINE leeren Versprechen
- Am Ende: CTA zum AI Income Machine Blueprint (${PRODUCT_URL}) — maximal 2 Sätze
- Wenn Affiliate-Bezug passt, erwähne das Affiliate-Programm (${AFFILIATE_URL})
- Format: Fließtext mit H2/H3 Überschriften als Markdown (##, ###)
- Kein HTML, nur Markdown

Beginne direkt mit dem Artikel-Inhalt (keine Einleitung oder Meta-Kommentare).`;

  const r = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${OPENAI_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 2000,
      temperature: 0.7,
    }),
  });
  if (!r.ok) throw new Error(`OpenAI ${r.status}: ${await r.text().then(t => t.substring(0, 200))}`);
  const data = await r.json();
  return data.choices[0].message.content;
}

function markdownToHtml(md) {
  return md
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(.+)$/, '<p>$1')
    .replace(/(<p>.*<\/p>)$/, '$1</p>');
}

function buildHtmlPage(topic, articleMd, dateStr) {
  const articleHtml = markdownToHtml(articleMd);
  return `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${topic.title}</title>
  <meta name="description" content="${topic.desc}" />
  <meta name="keywords" content="${topic.keyword}, KI Einkommen, passives Einkommen, Deutschland 2026" />
  <link rel="canonical" href="https://${SITE_HOST}/${topic.slug}.html" />
  <meta property="og:title" content="${topic.title}" />
  <meta property="og:description" content="${topic.desc}" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="https://${SITE_HOST}/${topic.slug}.html" />
  <meta property="article:published_time" content="${dateStr}" />
  <meta property="article:author" content="Rudolf Sarkany" />
  <script type="application/ld+json">
  {"@context":"https://schema.org","@type":"Article","headline":"${topic.title}","description":"${topic.desc}","author":{"@type":"Person","name":"Rudolf Sarkany"},"publisher":{"@type":"Organization","name":"AiiteC"},"datePublished":"${dateStr}","url":"https://${SITE_HOST}/${topic.slug}.html"}
  </script>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f1a;color:#e2e8f0;line-height:1.8}
    nav{background:rgba(15,15,26,0.95);padding:16px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.05);position:sticky;top:0;z-index:100;backdrop-filter:blur(10px)}
    .logo{font-size:1.1rem;font-weight:800;color:white;text-decoration:none}
    .logo span{color:#7c3aed}
    .nav-cta{background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:8px 20px;border-radius:50px;font-size:.85rem;font-weight:700;text-decoration:none}
    .hero{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:50px 20px;border-bottom:1px solid rgba(255,255,255,0.06)}
    .hero-inner{max-width:800px;margin:0 auto}
    .hero-meta{font-size:.85rem;color:#64748b;margin-bottom:16px}
    h1{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:900;line-height:1.2;margin-bottom:16px}
    .hero-desc{color:#94a3b8;font-size:1.05rem}
    article{max-width:800px;margin:0 auto;padding:40px 20px}
    h2{font-size:1.6rem;font-weight:800;color:#f1f5f9;margin:40px 0 16px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.06)}
    h2:first-of-type{border-top:none;margin-top:0}
    h3{font-size:1.2rem;font-weight:700;color:#e2e8f0;margin:28px 0 10px}
    p{color:#94a3b8;margin-bottom:18px}
    strong{color:#e2e8f0}
    a{color:#a78bfa;text-decoration:none}
    a:hover{text-decoration:underline}
    .cta-box{background:linear-gradient(135deg,rgba(124,58,237,.15),rgba(91,33,182,.08));border:2px solid #7c3aed;border-radius:16px;padding:28px;text-align:center;margin:40px 0}
    .cta-box h3{font-size:1.2rem;color:white;margin-bottom:8px}
    .cta-box p{color:#94a3b8;margin-bottom:20px;font-size:.95rem}
    .cta-box a{display:inline-block;background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:14px 32px;border-radius:50px;font-size:1rem;font-weight:700;text-decoration:none}
    footer{background:rgba(0,0,0,.3);padding:30px 20px;text-align:center;color:#475569;font-size:.85rem;border-top:1px solid rgba(255,255,255,.05);margin-top:50px}
    footer a{color:#64748b;text-decoration:none;margin:0 8px}
  </style>
</head>
<body>
<nav>
  <a href="/" class="logo">AI<span>Income</span></a>
  <a href="/checkliste.html" class="nav-cta">Gratis Checkliste</a>
</nav>
<div class="hero">
  <div class="hero-inner">
    <div class="hero-meta">📅 ${dateStr} &nbsp;|&nbsp; ✍️ Rudolf Sarkany &nbsp;|&nbsp; ⏱️ 8 Minuten Lesezeit</div>
    <h1>${topic.title}</h1>
    <p class="hero-desc">${topic.desc}</p>
  </div>
</div>
<article>
${articleHtml}
<div class="cta-box">
  <h3>Bereit mit KI Einkommen aufzubauen?</h3>
  <p>Der AI Income Machine 90-Day Blueprint zeigt dir Schritt für Schritt wie das geht — auf Deutsch, €37 Einmalzahlung.</p>
  <a href="${PRODUCT_URL}" target="_blank">Jetzt starten →</a>
</div>
</article>
<footer>
  <a href="/">Startseite</a>
  <a href="/ki-geld-verdienen.html">KI Methoden</a>
  <a href="/checkliste.html">Gratis Checkliste</a>
  <a href="/affiliate.html">Affiliate Programm</a>
  <p style="margin-top:12px">© 2026 AiiteC — Rudolf Sarkany</p>
</footer>
</body>
</html>`;
}

async function submitToIndexNow(slug) {
  const url = `https://${SITE_HOST}/${slug}.html`;
  try {
    await fetch('https://api.indexnow.org/IndexNow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        host: SITE_HOST,
        key: INDEXNOW_KEY,
        keyLocation: `https://${SITE_HOST}/${INDEXNOW_KEY}.txt`,
        urlList: [url],
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

  // Rotate topic by week
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const topic = ARTICLE_TOPICS[weekNum % ARTICLE_TOPICS.length];
  const dateStr = new Date().toISOString().split('T')[0];

  let articleMd;
  try {
    articleMd = await generateArticle(topic);
  } catch (err) {
    await sendTelegram(`❌ SEO Writer: OpenAI Fehler: ${err.message.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err.message });
  }

  const html = buildHtmlPage(topic, articleMd, dateStr);

  // Note: Vercel functions cannot write to the filesystem persistently.
  // The generated HTML is returned in the response so it can be saved via webhook or CI.
  // For now, submit the URL to IndexNow optimistically.
  await submitToIndexNow(topic.slug);

  const pageUrl = `https://${SITE_HOST}/${topic.slug}.html`;

  await sendTelegram(
    `✍️ <b>SEO Artikel generiert!</b>\n\n📝 <b>${topic.title}</b>\n🔑 Keyword: ${topic.keyword}\n🔗 ${pageUrl}\n\n<i>Artikel wurde generiert. HTML muss noch deployed werden.</i>\nSlug: ${topic.slug}.html`
  );

  return res.status(200).json({
    ok: true,
    topic: topic.slug,
    title: topic.title,
    pageUrl,
    htmlLength: html.length,
    html,
  });
}
