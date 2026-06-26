// Dynamic SEO Blog Endpoint
// Serves articles stored in Supabase seo_content table
// URL pattern: /blog/:slug (rewritten from vercel.json)
// GET /api/blog?slug=ki-geld-verdienen → returns full HTML page

const SUPABASE_URL = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const SUPABASE_ANON = process.env.SUPABASE_ANON_KEY;
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';

async function fetchArticle(slug) {
  const url = `${SUPABASE_URL}/rest/v1/seo_content?slug=eq.${encodeURIComponent(slug)}&published=eq.true&select=*&limit=1`;
  const r = await fetch(url, {
    headers: {
      apikey: SUPABASE_ANON,
      Authorization: `Bearer ${SUPABASE_ANON}`,
    },
  });
  if (!r.ok) throw new Error(`Supabase ${r.status}`);
  const rows = await r.json();
  return rows[0] || null;
}

async function fetchAllSlugs() {
  const url = `${SUPABASE_URL}/rest/v1/seo_content?published=eq.true&select=slug,title,meta_description,created_at&order=created_at.desc&limit=200`;
  const r = await fetch(url, {
    headers: {
      apikey: SUPABASE_ANON,
      Authorization: `Bearer ${SUPABASE_ANON}`,
    },
  });
  if (!r.ok) throw new Error(`Supabase ${r.status}`);
  return r.json();
}

async function fetchRelated(currentSlug) {
  // Pseudo-random offset per slug so each article links to different related articles
  const offset = currentSlug.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 80;
  const url = `${SUPABASE_URL}/rest/v1/seo_content?published=eq.true&slug=neq.${encodeURIComponent(currentSlug)}&select=slug,title,meta_description&order=id.asc&limit=4&offset=${offset}`;
  try {
    const r = await fetch(url, { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` } });
    return r.ok ? r.json() : [];
  } catch { return []; }
}

function buildArticlePage(article, related = []) {
  const dateStr = article.created_at
    ? new Date(article.created_at).toISOString().split('T')[0]
    : '2026-06-24';

  return `<!DOCTYPE html>
<html lang="${article.language || 'de'}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${article.title}</title>
  <meta name="description" content="${article.meta_description || ''}" />
  <link rel="canonical" href="https://autoincome-ai.vercel.app/blog/${article.slug}" />
  <meta property="og:title" content="${article.title}" />
  <meta property="og:description" content="${article.meta_description || ''}" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="https://autoincome-ai.vercel.app/blog/${article.slug}" />
  <meta property="article:published_time" content="${dateStr}" />
  <meta property="og:image" content="https://autoincome-ai.vercel.app/og-image.png" />
  <script type="application/ld+json">${JSON.stringify({
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": article.title,
    "description": article.meta_description || '',
    "datePublished": dateStr,
    "dateModified": dateStr,
    "author": { "@type": "Person", "name": "Rudolf Sarkany", "url": "https://autoincome-ai.vercel.app" },
    "publisher": { "@type": "Organization", "name": "AiiteC", "url": "https://autoincome-ai.vercel.app", "logo": { "@type": "ImageObject", "url": "https://autoincome-ai.vercel.app/og-image.png" } },
    "mainEntityOfPage": { "@type": "WebPage", "@id": `https://autoincome-ai.vercel.app/blog/${article.slug}` },
    "inLanguage": article.language || "de",
    "keywords": article.keyword || article.title
  })}</script>
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
    h1{font-size:clamp(1.8rem,4vw,3rem);font-weight:900;line-height:1.2;margin-bottom:16px}
    article{max-width:800px;margin:0 auto;padding:40px 20px}
    article h2{font-size:1.6rem;font-weight:800;color:#f1f5f9;margin:40px 0 16px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.06)}
    article h3{font-size:1.2rem;font-weight:700;color:#e2e8f0;margin:24px 0 10px}
    article p{color:#94a3b8;margin-bottom:18px}
    article strong{color:#e2e8f0}
    article a{color:#a78bfa;text-decoration:none}
    article a:hover{text-decoration:underline}
    article ul,article ol{padding-left:24px;margin-bottom:18px}
    article li{color:#94a3b8;margin-bottom:6px}
    .cta-box{background:linear-gradient(135deg,rgba(124,58,237,.15),rgba(91,33,182,.08));border:2px solid #7c3aed;border-radius:16px;padding:32px;text-align:center;margin:40px 0;position:relative}
    .cta-box .cta-badge{display:inline-block;background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.3);padding:3px 12px;border-radius:99px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
    .cta-box h3{font-size:1.4rem;color:white;margin-bottom:8px}
    .cta-box p{color:#94a3b8;margin-bottom:16px;font-size:.95rem}
    .cta-box .cta-social{display:flex;justify-content:center;gap:16px;flex-wrap:wrap;margin-bottom:20px}
    .cta-box .cta-social span{color:#10b981;font-size:.85rem;font-weight:600}
    .cta-box a.cta-btn{display:inline-block;background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:15px 36px;border-radius:50px;font-size:1rem;font-weight:700;text-decoration:none;box-shadow:0 4px 20px rgba(124,58,237,.4)}
    .cta-box .cta-guarantee{margin-top:10px;font-size:.8rem;color:#64748b}
    .email-box{background:rgba(16,185,129,.06);border:1px solid rgba(16,185,129,.25);border-radius:16px;padding:28px;text-align:center;margin:32px 0}
    .email-box h3{font-size:1.1rem;color:#10b981;margin-bottom:6px}
    .email-box p{color:#94a3b8;margin-bottom:16px;font-size:.9rem}
    .email-box form{display:flex;gap:8px;max-width:400px;margin:0 auto;flex-wrap:wrap;justify-content:center}
    .email-box input{flex:1;min-width:200px;padding:12px 16px;border-radius:8px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.05);color:#e2e8f0;font-size:.95rem}
    .email-box button{background:#10b981;color:white;border:none;padding:12px 24px;border-radius:8px;font-weight:700;cursor:pointer;font-size:.95rem}
    .related{max-width:800px;margin:40px auto;padding:0 20px}
    .related h3{font-size:1.1rem;font-weight:700;color:#94a3b8;margin-bottom:16px;text-transform:uppercase;letter-spacing:.05em;font-size:.8rem}
    .related-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
    .related-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:16px;text-decoration:none;display:block}
    .related-card:hover{border-color:#7c3aed}
    .related-card h4{font-size:.9rem;font-weight:700;color:#e2e8f0;margin-bottom:6px;line-height:1.4}
    .related-card p{font-size:.8rem;color:#64748b}
    footer{background:rgba(0,0,0,.3);padding:30px 20px;text-align:center;color:#475569;font-size:.85rem;border-top:1px solid rgba(255,255,255,.05);margin-top:50px}
    footer a{color:#64748b;text-decoration:none;margin:0 8px}
  </style>
</head>
<body>
<nav>
  <a href="/" class="logo">AI<span>Income</span></a>
  <div style="display:flex;gap:8px;align-items:center;">
    <a href="/checkliste.html" style="color:#94a3b8;font-size:.85rem;text-decoration:none;">Gratis Checkliste</a>
    <a href="https://www.checkout-ds24.com/product/668035" class="nav-cta">Blueprint €37 →</a>
  </div>
</nav>
<div class="hero">
  <div class="hero-inner">
    <div class="hero-meta">📅 ${dateStr} &nbsp;|&nbsp; ✍️ Rudolf Sarkany</div>
    <h1>${article.title}</h1>
    <p style="color:#94a3b8;font-size:1.05rem">${article.meta_description || ''}</p>
  </div>
</div>
<article>
${article.content_html || '<p>Artikel wird geladen...</p>'}
<div class="email-box">
  <h3>Gratis: KI-Einkommen Checkliste</h3>
  <p>7 Schritte zum ersten automatischen Einkommen — sofort als PDF.</p>
  <form action="https://manage.kmail-lists.com/subscriptions/subscribe" method="POST" target="_blank">
    <input type="hidden" name="g" value="Xwxq6V" />
    <input type="hidden" name="a" value="VaCYq3" />
    <input type="hidden" name="$fields" value="$source" />
    <input type="hidden" name="$source" value="blog-${article.slug}" />
    <input type="email" name="email" placeholder="deine@email.de" required />
    <button type="submit">Kostenlos holen</button>
  </form>
</div>
<div class="cta-box">
  <div class="cta-badge">⭐ 60-Tage Geld-zurück-Garantie</div>
  <h3>Bereit, mit KI passives Einkommen aufzubauen?</h3>
  <p>Der AI Income Machine 90-Day Blueprint — Schritt-für-Schritt auf Deutsch, €37 Einmalzahlung.</p>
  <div class="cta-social">
    <span>✅ Kein Abo</span>
    <span>✅ Sofortzugang</span>
    <span>✅ 60 Tage Garantie</span>
  </div>
  <a href="${PRODUCT_URL}" class="cta-btn" target="_blank">Jetzt für €37 starten →</a>
  <p class="cta-guarantee">60-Tage Geld-zurück-Garantie · Digistore24 sichere Zahlung</p>
</div>
${article.faq_html ? `<section class="faq">${article.faq_html}</section>` : ''}
</article>
${related.length > 0 ? `
<div class="related">
  <h3>Das könnte dich auch interessieren</h3>
  <div class="related-grid">
    ${related.map((r) => `<a href="/blog/${r.slug}" class="related-card"><h4>${r.title}</h4><p>${(r.meta_description || '').substring(0, 90)}…</p></a>`).join('')}
  </div>
</div>` : ''}
<footer>
  <a href="/">Startseite</a>
  <a href="/blog">Alle Artikel</a>
  <a href="/checkliste.html">Gratis Checkliste</a>
  <a href="/affiliate.html">Affiliate</a>
  <p style="margin-top:12px">© 2026 AiiteC — Rudolf Sarkany</p>
</footer>
<div id="sticky-cta" style="display:none;position:fixed;bottom:0;left:0;right:0;z-index:999;background:linear-gradient(135deg,#1a0533,#16213e);border-top:1px solid rgba(124,58,237,.4);padding:12px 20px;box-shadow:0 -4px 24px rgba(0,0,0,.5);">
  <div style="max-width:800px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
    <div style="flex:1;min-width:200px;">
      <p style="margin:0;font-size:.8rem;color:#a78bfa;font-weight:700;text-transform:uppercase;letter-spacing:1px;">90-Tage Blueprint</p>
      <p style="margin:4px 0 0;font-size:.93rem;color:#f1f5f9;font-weight:600;">Passives KI-Einkommen — Auf Deutsch · €37</p>
    </div>
    <div style="display:flex;gap:10px;align-items:center;flex-shrink:0;">
      <a href="https://www.checkout-ds24.com/product/668035" style="background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:11px 28px;border-radius:50px;font-size:.9rem;font-weight:700;text-decoration:none;white-space:nowrap;">Jetzt für €37 →</a>
      <button onclick="document.getElementById('sticky-cta').style.display='none'" style="background:none;border:none;color:#64748b;font-size:1.2rem;cursor:pointer;padding:4px 8px;line-height:1;">✕</button>
    </div>
  </div>
</div>
<script>
(function(){
  var shown=false;
  window.addEventListener('scroll',function(){
    if(shown)return;
    var pct=window.scrollY/(document.body.scrollHeight-window.innerHeight);
    if(pct>0.3){shown=true;document.getElementById('sticky-cta').style.display='block';}
  },{passive:true});
})();
</script>
<div id="exit-popup" style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);justify-content:center;align-items:center;">
  <div style="background:linear-gradient(135deg,#1e1b4b,#1a0533);border:1px solid rgba(124,58,237,.5);border-radius:20px;padding:40px 36px;max-width:480px;width:90%;position:relative;text-align:center;box-shadow:0 24px 64px rgba(0,0,0,.6);">
    <button onclick="document.getElementById('exit-popup').style.display='none'" style="position:absolute;top:14px;right:18px;background:none;border:none;color:#64748b;font-size:1.4rem;cursor:pointer;line-height:1;">✕</button>
    <div style="font-size:2.5rem;margin-bottom:12px;">⏳</div>
    <h2 style="color:#f1f5f9;font-size:1.4rem;margin:0 0 10px;font-weight:800;">Warte — lies das bevor du gehst</h2>
    <p style="color:#94a3b8;font-size:.95rem;margin:0 0 20px;line-height:1.6;">Der AI Income Machine Blueprint zeigt dir in 90 Tagen wie du mit KI automatisch Geld verdienst — auf Deutsch, Schritt für Schritt, €37 einmalig.</p>
    <div style="display:flex;gap:8px;justify-content:center;margin-bottom:20px;flex-wrap:wrap;">
      <span style="background:rgba(124,58,237,.2);color:#a78bfa;padding:4px 12px;border-radius:20px;font-size:.8rem;">✅ Sofortzugang</span>
      <span style="background:rgba(124,58,237,.2);color:#a78bfa;padding:4px 12px;border-radius:20px;font-size:.8rem;">✅ 60 Tage Garantie</span>
      <span style="background:rgba(124,58,237,.2);color:#a78bfa;padding:4px 12px;border-radius:20px;font-size:.8rem;">✅ Kein Abo</span>
    </div>
    <a href="https://www.checkout-ds24.com/product/668035" onclick="document.getElementById('exit-popup').style.display='none'" style="display:block;background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:14px 32px;border-radius:50px;font-size:1rem;font-weight:700;text-decoration:none;margin-bottom:12px;">Jetzt Blueprint holen — €37 →</a>
    <button onclick="document.getElementById('exit-popup').style.display='none'" style="background:none;border:none;color:#475569;font-size:.82rem;cursor:pointer;text-decoration:underline;">Nein danke, ich verzichte</button>
  </div>
</div>
<script>
(function(){
  var ep=document.getElementById('exit-popup');
  var dismissed=sessionStorage.getItem('exit-dismissed');
  if(dismissed)return;
  document.addEventListener('mouseleave',function(e){
    if(e.clientY<=0&&ep.style.display==='none'){
      ep.style.display='flex';
      sessionStorage.setItem('exit-dismissed','1');
    }
  });
})();
</script>
</body>
</html>`;
}

function buildIndexPage(articles) {
  const cards = articles.map((a) => `
    <a href="/blog/${a.slug}" class="card">
      <h2>${a.title}</h2>
      <p>${a.meta_description || ''}</p>
      <span class="read-more">Lesen →</span>
    </a>`).join('');

  return `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>KI Einkommen Blog — Alle Artikel</title>
  <meta name="description" content="Alle Artikel über KI-Einkommen, Digistore24, passives Einkommen und Automatisierung auf Deutsch." />
  <link rel="canonical" href="https://autoincome-ai.vercel.app/blog" />
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f1a;color:#e2e8f0;line-height:1.7}
    nav{background:rgba(15,15,26,0.95);padding:16px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.05);position:sticky;top:0;z-index:100;backdrop-filter:blur(10px)}
    .logo{font-size:1.1rem;font-weight:800;color:white;text-decoration:none}
    .logo span{color:#7c3aed}
    .nav-cta{background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:8px 20px;border-radius:50px;font-size:.85rem;font-weight:700;text-decoration:none}
    .hero{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:50px 20px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06)}
    h1{font-size:clamp(1.8rem,4vw,2.5rem);font-weight:900;margin-bottom:12px}
    .hero p{color:#94a3b8;font-size:1.05rem}
    .grid{max-width:900px;margin:40px auto;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}
    .card{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px;text-decoration:none;display:block;transition:border-color 0.2s}
    .card:hover{border-color:#7c3aed}
    .card h2{font-size:1.1rem;font-weight:700;color:#e2e8f0;margin-bottom:10px;line-height:1.4}
    .card p{color:#64748b;font-size:0.9rem;margin-bottom:16px}
    .card .read-more{color:#a78bfa;font-size:0.9rem;font-weight:600}
    .empty{text-align:center;padding:60px 20px;color:#475569}
    footer{background:rgba(0,0,0,.3);padding:30px 20px;text-align:center;color:#475569;font-size:.85rem;border-top:1px solid rgba(255,255,255,.05);margin-top:50px}
    footer a{color:#64748b;text-decoration:none;margin:0 8px}
  </style>
</head>
<body>
<nav>
  <a href="/" class="logo">AI<span>Income</span></a>
  <div style="display:flex;gap:8px;align-items:center;">
    <a href="/checkliste.html" style="color:#94a3b8;font-size:.85rem;text-decoration:none;">Gratis Checkliste</a>
    <a href="https://www.checkout-ds24.com/product/668035" class="nav-cta">Blueprint €37 →</a>
  </div>
</nav>
<div class="hero">
  <h1>KI Einkommen Blog</h1>
  <p>${articles.length} Artikel über KI, passives Einkommen und Automatisierung — auf Deutsch.</p>
  <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:24px;">
    <a href="/blog/ki-einkommen-1000-euro-monat" style="background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.4);color:#a78bfa;padding:8px 18px;border-radius:50px;font-size:.85rem;text-decoration:none;">💶 1000€/Monat</a>
    <a href="/blog/digistore24-affiliate-tipps-2026" style="background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.4);color:#a78bfa;padding:8px 18px;border-radius:50px;font-size:.85rem;text-decoration:none;">🎯 Affiliate</a>
    <a href="/blog/ai-income-machine-blueprint-erfahrungen" style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.4);color:#f59e0b;padding:8px 18px;border-radius:50px;font-size:.85rem;text-decoration:none;">⭐ Blueprint Review</a>
    <a href="/blog/ki-geld-verdienen-ohne-erfahrung" style="background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.4);color:#a78bfa;padding:8px 18px;border-radius:50px;font-size:.85rem;text-decoration:none;">🚀 Für Anfänger</a>
    <a href="/blog/passives-einkommen-software-vergleich" style="background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.4);color:#a78bfa;padding:8px 18px;border-radius:50px;font-size:.85rem;text-decoration:none;">🔧 Tools</a>
  </div>
</div>
<div style="max-width:900px;margin:0 auto;padding:24px 20px 0;background:linear-gradient(135deg,rgba(124,58,237,.08),rgba(16,185,129,.05));border:1px solid rgba(124,58,237,.2);border-radius:16px;">
  <div style="display:flex;flex-wrap:wrap;gap:20px;align-items:center;justify-content:space-between;">
    <div>
      <p style="font-size:.75rem;color:#f59e0b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">NEU</p>
      <p style="font-size:1.05rem;font-weight:700;color:#f1f5f9;margin-bottom:4px;">90-Tage Blueprint: Dein Plan zum ersten KI-Einkommen</p>
      <p style="font-size:.85rem;color:#94a3b8;">Einmalig €37 · 60-Tage-Garantie · Sofortzugang · Auf Deutsch</p>
    </div>
    <a href="https://www.checkout-ds24.com/product/668035" style="flex-shrink:0;background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:12px 28px;border-radius:50px;font-weight:700;text-decoration:none;font-size:.95rem;">Jetzt für €37 →</a>
  </div>
</div>
${articles.length > 0
  ? `<div class="grid">${cards}</div>`
  : '<div class="empty"><p>Artikel werden bald verfügbar.</p></div>'}
<footer>
  <a href="/">Startseite</a>
  <a href="/checkliste.html">Gratis Checkliste</a>
  <a href="/affiliate.html">Affiliate</a>
  <a href="https://www.checkout-ds24.com/product/668035" target="_blank">Produkt</a>
  <p style="margin-top:12px">© 2026 AiiteC — Rudolf Sarkany</p>
</footer>
</body>
</html>`;
}

export default async function handler(req, res) {
  if (!SUPABASE_ANON) {
    return res.status(500).send('Supabase not configured');
  }

  const slug = req.query?.slug;

  // Blog index: /blog (no slug)
  if (!slug || slug === 'index') {
    try {
      const articles = await fetchAllSlugs();
      const html = buildIndexPage(articles);
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      return res.status(200).send(html);
    } catch (err) {
      return res.status(500).send(`<h1>Error</h1><p>${err.message}</p>`);
    }
  }

  // Article page
  try {
    const [article, related] = await Promise.all([fetchArticle(slug), fetchRelated(slug)]);
    if (!article) {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      return res.status(404).send(`<!DOCTYPE html><html><body style="font-family:sans-serif;background:#0f0f1a;color:#e2e8f0;padding:40px;text-align:center"><h1>Artikel nicht gefunden</h1><p><a href="/blog" style="color:#a78bfa">← Alle Artikel</a></p></body></html>`);
    }
    const html = buildArticlePage(article, related);
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).send(html);
  } catch (err) {
    return res.status(500).send(`<h1>Error</h1><p>${err.message}</p>`);
  }
}
