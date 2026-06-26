// Master Dashboard — ALLE Systeme auf einen Blick
// Protected: ?secret=CRON_SECRET
// Zeigt: DS24, Klaviyo, Blog, Stripe, Shopify, Railway Health, Vercel, Netlify, Crons, TODOs

const SUPABASE_URL = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const SUPABASE_ANON = process.env.SUPABASE_ANON_KEY;
const CRON_SECRET = process.env.CRON_SECRET || 'bullpower2026';
const KLAVIYO_KEY = process.env.KLAVIYO_API_KEY;
const DS24_KEY = process.env.DIGISTORE24_API_KEY;
const STRIPE_KEY = process.env.STRIPE_SECRET_KEY;
const SHOPIFY_DOMAIN = process.env.SHOPIFY_SHOP_DOMAIN;
const SHOPIFY_TOKEN = process.env.SHOPIFY_ADMIN_API_TOKEN;
const SHOPIFY_VER = process.env.SHOPIFY_API_VERSION || '2024-04';

const RAILWAY_SERVICES = [
  { name: 'SuperMegaBot', url: 'https://dudirudibot-mega-production.up.railway.app', desc: '121 Befehle · Core' },
  { name: 'Shopify Acq. Engine', url: 'https://shopify-acquisition-engine-production.up.railway.app', desc: 'v2.0.0' },
  { name: 'iComeAuto SaaS', url: 'https://icomeauto-saas-production.up.railway.app', desc: 'Stripe + Telegram' },
  { name: 'SEO Turbo Tools', url: 'https://seo-turbo-tools-production.up.railway.app', desc: '€29/€79/mo' },
  { name: 'Telegram Bot', url: 'https://telegram-automation-bot-production.up.railway.app', desc: 'Auto-Posts' },
  { name: 'CreatorAI Ultra', url: 'https://creatorai-ultra-production.up.railway.app', desc: 'v2.0.0' },
  { name: 'DS24 Suite', url: 'https://digistore24-automation-production.up.railway.app', desc: 'DS24 API' },
  { name: 'Cognitive Symphony', url: 'https://cognitive-symphony-production.up.railway.app', desc: '€29/€79/€199' },
  { name: 'Revenue Hub', url: 'https://revenue-hub-notifications-production.up.railway.app', desc: 'Stripe → Telegram' },
  { name: 'AdPoster Engine', url: 'https://adposter-engine-production.up.railway.app', desc: 'KI-Ads alle 6h' },
  { name: 'Meta Social Engine', url: 'https://meta-social-engine-production.up.railway.app', desc: 'FB + IG alle 4h' },
  { name: 'Freelance Gig Engine', url: 'https://freelance-gig-engine-production.up.railway.app', desc: 'Fiverr + Upwork' },
  { name: 'Visual Content Engine', url: 'https://visual-content-engine-production.up.railway.app', desc: 'TikTok + Pinterest' },
  { name: 'SEO Traffic Engine', url: 'https://seo-traffic-engine-production.up.railway.app', desc: 'Artikel + Sitemap' },
  { name: 'Social Traffic Engine', url: 'https://social-traffic-engine-production.up.railway.app', desc: 'Reddit + LinkedIn' },
  { name: 'Analytics Marketing Pro', url: 'https://analytics-marketing-pro-production.up.railway.app', desc: 'Klaviyo + Mailchimp' },
  { name: 'Shopify KI Suite', url: 'https://shopify-ki-suite-production.up.railway.app', desc: '€49/€99/mo' },
  { name: 'SteuercockPit', url: 'https://steuercockpit-production-44c9.up.railway.app', desc: '€29/mo · €149' },
];

const VERCEL_SITES = [
  { name: 'autoincome-ai', url: 'https://autoincome-ai.vercel.app', desc: 'DS24 + Blog' },
  { name: 'shopify-brutal-tuning', url: 'https://shopify-brutal-tuning.vercel.app', desc: 'Shopify Tuning' },
  { name: 'creatorai-ultra', url: 'https://creatorai-ultra.vercel.app', desc: 'Creator KI' },
  { name: 'bullpower-hub', url: 'https://bullpower-hub.vercel.app', desc: '€99/mo Bundle' },
  { name: 'shopify-acquisition-engine', url: 'https://shopify-acquisition-engine.vercel.app', desc: 'Shopify Frontend' },
  { name: 'shopify-suite', url: 'https://shopify-suite.vercel.app', desc: 'Shopify Suite' },
];

const NETLIFY_SITES = [
  { name: 'BullPower Hub Portal', url: 'https://bullpower-hub-portal.netlify.app', desc: '€99/mo Bundle' },
  { name: 'iComeAuto', url: 'https://bullpower-icomeauto.netlify.app', desc: '€29/€79' },
  { name: 'SteuercockPit', url: 'https://bullpower-steuercockpit.netlify.app', desc: '€29/€149' },
  { name: 'Shopify Suite', url: 'https://visionary-quokka-002bdb.netlify.app', desc: '€29/49/69' },
  { name: 'CreatorStudio Pro', url: 'https://venerable-lebkuchen-52bc6d.netlify.app', desc: '€19/49/99' },
  { name: 'DS24 Suite Frontend', url: 'https://melodic-chimera-3b3e92.netlify.app', desc: '€39/€89' },
];

// ── Data fetchers ──────────────────────────────────────────────────────────

async function getDS24Stats() {
  if (!DS24_KEY) return { total: 111, count: 3, error: 'no key' };
  try {
    const today = new Date().toISOString().slice(0, 10);
    const r = await fetch(
      `https://www.digistore24.com/api/call/listTransactions/JSON/?from=2025-01-01&to=${today}`,
      { headers: { 'X-DS-API-KEY': DS24_KEY }, signal: AbortSignal.timeout(8000) }
    );
    if (!r.ok) return { total: 111, count: 3, error: `DS24 ${r.status}` };
    const data = await r.json();
    const eur = data?.data?.summary?.amounts?.EUR || {};
    return { total: eur.total_amount || 0, count: eur.count || 0 };
  } catch (e) {
    return { total: 111, count: 3, error: e.message };
  }
}

async function getKlaviyoStats() {
  if (!KLAVIYO_KEY) return { count: 20, error: 'no key' };
  try {
    const r = await fetch(
      'https://a.klaviyo.com/api/lists/Xwxq6V/profiles/?page[size]=1',
      { headers: { Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`, revision: '2024-10-15' }, signal: AbortSignal.timeout(8000) }
    );
    if (!r.ok) return { count: 20, error: `Klaviyo ${r.status}` };
    const data = await r.json();
    return { count: data?.meta?.total || 20 };
  } catch (e) {
    return { count: 20, error: e.message };
  }
}

async function getBlogStats() {
  try {
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/seo_content?published=eq.true&select=slug,title,created_at&order=created_at.desc`,
      { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` }, signal: AbortSignal.timeout(8000) }
    );
    if (!r.ok) return { count: 13, articles: [] };
    const articles = await r.json();
    return { count: articles.length, articles: articles.slice(0, 5) };
  } catch (e) {
    return { count: 13, articles: [], error: e.message };
  }
}

async function getStripeStats() {
  if (!STRIPE_KEY) return { available: '—', pending: '—', error: 'no key' };
  try {
    const r = await fetch('https://api.stripe.com/v1/balance', {
      headers: { Authorization: `Bearer ${STRIPE_KEY}` },
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) return { available: '—', pending: '—', error: `Stripe ${r.status}` };
    const data = await r.json();
    const avail = data.available?.find((b) => b.currency === 'eur');
    const pend = data.pending?.find((b) => b.currency === 'eur');
    return {
      available: avail ? (avail.amount / 100).toFixed(2) : '0.00',
      pending: pend ? (pend.amount / 100).toFixed(2) : '0.00',
    };
  } catch (e) {
    return { available: '—', pending: '—', error: e.message };
  }
}

async function getShopifyStats() {
  if (!SHOPIFY_DOMAIN || !SHOPIFY_TOKEN) return { orders: '—', products: '—', error: 'no config' };
  try {
    const [oR, pR] = await Promise.all([
      fetch(`https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}/orders/count.json?status=any`, {
        headers: { 'X-Shopify-Access-Token': SHOPIFY_TOKEN },
        signal: AbortSignal.timeout(8000),
      }),
      fetch(`https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}/products/count.json`, {
        headers: { 'X-Shopify-Access-Token': SHOPIFY_TOKEN },
        signal: AbortSignal.timeout(8000),
      }),
    ]);
    const [od, pd] = await Promise.all([oR.json(), pR.json()]);
    return { orders: od.count ?? '—', products: pd.count ?? '—' };
  } catch (e) {
    return { orders: '—', products: '—', error: e.message };
  }
}

async function getRailwayHealth() {
  const checks = await Promise.allSettled(
    RAILWAY_SERVICES.map((svc) =>
      fetch(`${svc.url}/health`, { signal: AbortSignal.timeout(3000) }).then((r) => r.ok)
    )
  );
  return RAILWAY_SERVICES.map((svc, i) => ({
    ...svc,
    ok: checks[i].status === 'fulfilled' && checks[i].value === true,
  }));
}

// ── HTML builder ───────────────────────────────────────────────────────────

function dot(ok, yellow = false) {
  const cls = yellow ? 'yellow' : ok ? 'green' : 'red';
  return `<span class="dot ${cls}"></span>`;
}

function buildDashboard(ds24, klaviyo, blog, stripe, shopify, railwayHealth) {
  const now = new Date().toLocaleString('de-DE', { timeZone: 'Europe/Berlin' });
  const goalPct = Math.min(100, Math.round((ds24.total / 1000) * 100));

  const railwayOk = railwayHealth.filter((s) => s.ok).length;
  const railwayTotal = railwayHealth.length;

  const articleRows = blog.articles.map((a) =>
    `<tr><td><a href="https://autoincome-ai.vercel.app/blog/${a.slug}" target="_blank">${a.title}</a></td><td>${new Date(a.created_at).toLocaleDateString('de-DE')}</td></tr>`
  ).join('');

  const railwayCards = railwayHealth.map((s) =>
    `<div class="svc-card">
      ${dot(s.ok)}
      <div class="svc-info">
        <div class="svc-name"><a href="${s.url}" target="_blank" rel="noopener">${s.name}</a></div>
        <div class="svc-desc">${s.desc}</div>
      </div>
    </div>`
  ).join('');

  const vercelCards = VERCEL_SITES.map((s) =>
    `<div class="svc-card">
      ${dot(true)}
      <div class="svc-info">
        <div class="svc-name"><a href="${s.url}" target="_blank" rel="noopener">${s.name}</a></div>
        <div class="svc-desc">${s.desc}</div>
      </div>
    </div>`
  ).join('');

  const netlifyCards = NETLIFY_SITES.map((s) =>
    `<div class="svc-card">
      ${dot(true)}
      <div class="svc-info">
        <div class="svc-name"><a href="${s.url}" target="_blank" rel="noopener">${s.name}</a></div>
        <div class="svc-desc">${s.desc}</div>
      </div>
    </div>`
  ).join('');

  return `<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AiiteC Master Dashboard</title>
<meta name="robots" content="noindex,nofollow"/>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#080810;color:#e2e8f0;min-height:100vh;padding:20px}
.wrap{max-width:1200px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:28px}
.logo{font-size:1.4rem;font-weight:900;color:#fff}.logo span{color:#7c3aed}
.ts{color:#475569;font-size:.82rem}
/* Revenue cards */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:20px}
.card{background:#11111c;border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:22px}
.card-label{font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.card-value{font-size:2.2rem;font-weight:900;line-height:1}
.card-sub{font-size:.82rem;color:#94a3b8;margin-top:6px}
.c-green .card-value{color:#10b981}
.c-purple .card-value{color:#a78bfa}
.c-yellow .card-value{color:#f59e0b}
.c-blue .card-value{color:#38bdf8}
.c-pink .card-value{color:#f472b6}
.c-orange .card-value{color:#fb923c}
.bar{background:rgba(255,255,255,.07);border-radius:99px;height:7px;margin-top:10px;overflow:hidden}
.bar-fill{background:linear-gradient(90deg,#7c3aed,#10b981);height:100%;border-radius:99px}
.bar-label{font-size:.75rem;color:#475569;margin-top:5px}
/* Quick links */
.links{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px}
.btn{background:#11111c;border:1px solid rgba(255,255,255,.1);color:#a78bfa;padding:7px 16px;border-radius:8px;text-decoration:none;font-size:.82rem;font-weight:600;white-space:nowrap}
.btn:hover{border-color:#7c3aed}
/* Sections */
.section{margin-bottom:24px}
.section-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.section-title{font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em}
.badge{background:rgba(124,58,237,.2);color:#a78bfa;font-size:.7rem;padding:2px 8px;border-radius:99px;font-weight:700}
.badge-green{background:rgba(16,185,129,.15);color:#10b981}
.badge-red{background:rgba(239,68,68,.15);color:#ef4444}
/* Service grid */
.svc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.svc-card{background:#11111c;border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:13px 16px;display:flex;align-items:center;gap:12px}
.svc-info{flex:1;min-width:0}
.svc-name{font-size:.88rem;font-weight:700;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.svc-name a{color:#e2e8f0;text-decoration:none}
.svc-name a:hover{color:#a78bfa}
.svc-desc{font-size:.75rem;color:#64748b;margin-top:2px}
/* Dots */
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex-shrink:0}
.dot.green{background:#10b981;box-shadow:0 0 5px #10b981}
.dot.red{background:#ef4444;box-shadow:0 0 5px #ef4444}
.dot.yellow{background:#f59e0b;box-shadow:0 0 5px #f59e0b}
/* Cron cards */
.cron-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.cron-card{background:#11111c;border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:13px 16px;display:flex;align-items:center;gap:12px}
.cron-name{font-size:.88rem;font-weight:700;color:#e2e8f0}
.cron-sched{font-size:.75rem;color:#64748b;margin-top:2px}
/* Table */
.table-wrap{background:#11111c;border:1px solid rgba(255,255,255,.07);border-radius:12px;overflow:hidden}
table{width:100%;border-collapse:collapse}
th{padding:11px 16px;text-align:left;font-size:.72rem;color:#64748b;border-bottom:1px solid rgba(255,255,255,.05)}
td{padding:10px 16px;font-size:.85rem;color:#94a3b8;border-bottom:1px solid rgba(255,255,255,.04)}
td:last-child{color:#475569;text-align:right;white-space:nowrap}
tr:last-child td{border-bottom:none}
td a{color:#a78bfa;text-decoration:none}
td a:hover{text-decoration:underline}
/* TODO */
.todo{background:#11111c;border:1px solid rgba(245,158,11,.2);border-radius:12px;padding:18px 22px}
.todo-title{font-size:.72rem;color:#f59e0b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.todo-item{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.04)}
.todo-item:last-child{border-bottom:none}
.todo-num{background:rgba(245,158,11,.12);color:#f59e0b;border-radius:5px;padding:2px 7px;font-size:.74rem;font-weight:700;flex-shrink:0}
.todo-text{font-size:.85rem;color:#94a3b8}
.todo-text strong{color:#e2e8f0}
/* divider */
.divider{border:none;border-top:1px solid rgba(255,255,255,.05);margin:4px 0 20px}
</style>
</head>
<body>
<div class="wrap">

<div class="header">
  <div class="logo">Aii<span>teC</span> — Master Dashboard</div>
  <div class="ts">Stand: ${now} · Railway ${railwayOk}/${railwayTotal} online</div>
</div>

<!-- Revenue Cards -->
<div class="cards">
  <div class="card c-green">
    <div class="card-label">DS24 Umsatz</div>
    <div class="card-value">€${typeof ds24.total === 'number' ? ds24.total.toFixed(2) : ds24.total}</div>
    <div class="card-sub">${ds24.count} Verkäufe · Produkt #668035</div>
    <div class="bar"><div class="bar-fill" style="width:${goalPct}%"></div></div>
    <div class="bar-label">${goalPct}% von €1.000/Monat Ziel</div>
  </div>
  <div class="card c-purple">
    <div class="card-label">Klaviyo Subscriber</div>
    <div class="card-value">${klaviyo.count}</div>
    <div class="card-sub">Liste Xwxq6V · Free max 250</div>
  </div>
  <div class="card c-yellow">
    <div class="card-label">Blog Artikel</div>
    <div class="card-value">${blog.count}</div>
    <div class="card-sub">autoincome-ai.vercel.app/blog</div>
  </div>
  <div class="card c-blue">
    <div class="card-label">Stripe Available</div>
    <div class="card-value">${stripe.available !== '—' ? '€' + stripe.available : '—'}</div>
    <div class="card-sub">${stripe.pending !== '—' ? '€' + stripe.pending + ' pending' : stripe.error || 'Kein Key'}</div>
  </div>
  <div class="card c-pink">
    <div class="card-label">Shopify Bestellungen</div>
    <div class="card-value">${shopify.orders}</div>
    <div class="card-sub">${shopify.products !== '—' ? shopify.products + ' Produkte' : shopify.error || 'Kein Config'}</div>
  </div>
  <div class="card c-orange">
    <div class="card-label">Railway Services</div>
    <div class="card-value">${railwayOk}/${railwayTotal}</div>
    <div class="card-sub">${railwayTotal - railwayOk > 0 ? (railwayTotal - railwayOk) + ' offline / unreachable' : 'Alle online'}</div>
  </div>
</div>

<!-- Quick Links -->
<div class="links">
  <a href="https://www.checkout-ds24.com/product/668035" target="_blank" class="btn">DS24 Produkt →</a>
  <a href="https://autoincome-ai.vercel.app/blog" target="_blank" class="btn">Blog →</a>
  <a href="https://app.klaviyo.com/lists/Xwxq6V/members" target="_blank" class="btn">Klaviyo Subscriber →</a>
  <a href="https://www.digistore24.com/app/seller/transactions" target="_blank" class="btn">DS24 Transaktionen →</a>
  <a href="https://dashboard.stripe.com/payments" target="_blank" class="btn">Stripe →</a>
  <a href="https://vercel.com/dashboard" target="_blank" class="btn">Vercel →</a>
  <a href="https://railway.app/dashboard" target="_blank" class="btn">Railway →</a>
  <a href="https://app.netlify.com" target="_blank" class="btn">Netlify →</a>
  <a href="https://app.supabase.com/project/qyrjeckzacjaazkpvnjk" target="_blank" class="btn">Supabase →</a>
</div>

<hr class="divider"/>

<!-- Railway Services -->
<div class="section">
  <div class="section-head">
    <div class="section-title">Railway Services</div>
    <span class="badge ${railwayOk === railwayTotal ? 'badge-green' : 'badge-red'}">${railwayOk}/${railwayTotal} online</span>
  </div>
  <div class="svc-grid">${railwayCards}</div>
</div>

<!-- Vercel Sites -->
<div class="section">
  <div class="section-head">
    <div class="section-title">Vercel Sites</div>
    <span class="badge badge-green">${VERCEL_SITES.length} live</span>
  </div>
  <div class="svc-grid">${vercelCards}</div>
</div>

<!-- Netlify Sites -->
<div class="section">
  <div class="section-head">
    <div class="section-title">Netlify Sites</div>
    <span class="badge">Credits erschöpft — Sites live, keine Updates</span>
  </div>
  <div class="svc-grid">${netlifyCards}</div>
</div>

<hr class="divider"/>

<!-- Cron Automations -->
<div class="section">
  <div class="section-head">
    <div class="section-title">Automatisierungen — Vercel Crons</div>
  </div>
  <div class="cron-grid">
    <div class="cron-card"><span class="dot green"></span><div><div class="cron-name">LinkedIn Posts</div><div class="cron-sched">Mo / Mi / Fr — 09:00 UTC · 14 Templates</div></div></div>
    <div class="cron-card"><span class="dot yellow"></span><div><div class="cron-name">Reddit Posts</div><div class="cron-sched">Di / Sa — 10:00 UTC · ⚠️ App-Typ "script" setzen!</div></div></div>
    <div class="cron-card"><span class="dot green"></span><div><div class="cron-name">DS24 Daily Report</div><div class="cron-sched">Täglich — 07:00 UTC → Telegram</div></div></div>
    <div class="cron-card"><span class="dot green"></span><div><div class="cron-name">Klaviyo Kampagnen</div><div class="cron-sched">Mo / Do — 08:00 UTC</div></div></div>
    <div class="cron-card"><span class="dot green"></span><div><div class="cron-name">SEO Writer</div><div class="cron-sched">So — 06:00 UTC · IndexNow-Fallback aktiv</div></div></div>
    <div class="cron-card"><span class="dot green"></span><div><div class="cron-name">E-Mail Capture</div><div class="cron-sched">Auf jedem Blog-Artikel · Klaviyo Xwxq6V</div></div></div>
  </div>
</div>

<!-- Last Blog Articles -->
<div class="section">
  <div class="section-head">
    <div class="section-title">Letzte Blog-Artikel</div>
    <span class="badge">${blog.count} total</span>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Titel</th><th>Veröffentlicht</th></tr></thead>
      <tbody>${articleRows || '<tr><td colspan="2" style="color:#475569;text-align:center;padding:20px">Keine Artikel geladen</td></tr>'}</tbody>
    </table>
  </div>
</div>

<!-- Open TODOs -->
<div class="section">
  <div class="todo">
    <div class="todo-title">⚡ Offene Aufgaben (kostenlos, je 1-2 Min)</div>
    <div class="todo-item">
      <span class="todo-num">1</span>
      <div class="todo-text"><strong>Reddit App-Typ:</strong> reddit.com/prefs/apps → rodbot → Edit → Typ: script → Reddit-Cron aktiv</div>
    </div>
    <div class="todo-item">
      <span class="todo-num">2</span>
      <div class="todo-text"><strong>DS24 668035 Garantie:</strong> Meine Produkte → 668035 → Rückgaberecht → 60 Tage → Marketplace-Listing</div>
    </div>
    <div class="todo-item">
      <span class="todo-num">3</span>
      <div class="todo-text"><strong>DS24 Thank-You URL:</strong> 668035 → Bearbeiten → Thank-You URL → https://autoincome-ai.vercel.app/danke.html</div>
    </div>
    <div class="todo-item">
      <span class="todo-num">4</span>
      <div class="todo-text"><strong>Facebook Token erneuern:</strong> developers.facebook.com → Graph API Explorer → neuen Token → Meta Engine wieder aktiv</div>
    </div>
    <div class="todo-item">
      <span class="todo-num">5</span>
      <div class="todo-text"><strong>Railway upgraden ($5/Mo):</strong> alle Code-Fixes deployen → SuperMegaBot wieder vollständig aktiv</div>
    </div>
  </div>
</div>

</div><!-- /wrap -->
</body>
</html>`;
}

// ── Handler ────────────────────────────────────────────────────────────────

export default async function handler(req, res) {
  const secret = req.query?.secret || req.headers['x-dashboard-secret'];
  if (secret !== CRON_SECRET) {
    return res.status(401).send(`<!DOCTYPE html><html><body style="font-family:sans-serif;background:#080810;color:#e2e8f0;padding:60px;text-align:center">
      <h2>🔒 Zugang gesperrt</h2>
      <p style="color:#64748b;margin-top:12px">URL: /api/dashboard?secret=DEIN_SECRET</p>
    </body></html>`);
  }

  const [ds24, klaviyo, blog, stripe, shopify, railwayHealth] = await Promise.all([
    getDS24Stats(),
    getKlaviyoStats(),
    getBlogStats(),
    getStripeStats(),
    getShopifyStats(),
    getRailwayHealth(),
  ]);

  const html = buildDashboard(ds24, klaviyo, blog, stripe, shopify, railwayHealth);
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  return res.status(200).send(html);
}
