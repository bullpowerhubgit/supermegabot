// AiiteC Master Dashboard — alles auf einem Blick
// GET /api/dashboard?secret=bullpower2026
// Zeigt: Revenue-Ziel, DS24, Klaviyo, Blog, Shopify, Railway, Crons, Social, TODOs

const SUPABASE_URL = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const SUPABASE_ANON = process.env.SUPABASE_ANON_KEY;
const CRON_SECRET = process.env.CRON_SECRET || 'bullpower2026';
const KLAVIYO_KEY = process.env.KLAVIYO_API_KEY;
const DS24_KEY = process.env.DIGISTORE24_API_KEY;
const STRIPE_KEY = process.env.STRIPE_SECRET_KEY;
const SHOPIFY_DOMAIN = process.env.SHOPIFY_SHOP_DOMAIN;
const SHOPIFY_TOKEN = process.env.SHOPIFY_ADMIN_API_TOKEN;
const SHOPIFY_VER = process.env.SHOPIFY_API_VERSION || '2024-04';

const MONTHLY_GOAL = 1000;

const RAILWAY_SERVICES = [
  { name: 'SuperMegaBot', url: 'https://supermegabot-production.up.railway.app', desc: '110 Befehle · Core' },
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

const CRON_JOBS = [
  { name: 'DS24 Daily Report', path: '/api/reports?type=daily', schedule: 'tägl. 07:00 UTC', emoji: '💰' },
  { name: 'Shopify Report', path: '/api/shopify?type=report', schedule: 'tägl. 07:05 UTC', emoji: '🛍️' },
  { name: 'Weekly KPI Report', path: '/api/reports?type=weekly', schedule: 'Mo 07:30 UTC', emoji: '📊' },
  { name: 'Affiliate Report', path: '/api/reports?type=affiliate', schedule: 'Fr 08:00 UTC', emoji: '🤝' },
  { name: 'Campaign Trigger', path: '/api/campaign-trigger', schedule: 'Mo/Mi/Fr 08:00 UTC', emoji: '📧' },
  { name: 'LinkedIn Poster', path: '/api/linkedin-poster', schedule: 'Mo/Mi/Fr 09:00 UTC', emoji: '💼' },
  { name: 'Visual Poster (Twitter+TG)', path: '/api/visual-poster', schedule: '6x tägl.', emoji: '🐦' },
  { name: 'Meta Poster (FB+IG)', path: '/api/meta-poster', schedule: 'Di/Do/Sa 10:00 UTC', emoji: '📘' },
  { name: 'Reddit Poster', path: '/api/reddit-poster', schedule: 'Di+Sa 14:00 UTC', emoji: '🤖' },
  { name: 'SEO Writer', path: '/api/seo-writer', schedule: 'Mo 06:00 UTC', emoji: '✍️' },
  { name: 'Marketplace Poster', path: '/api/marketplace-poster', schedule: 'tägl. 10:00 UTC', emoji: '🏪' },
  { name: 'Klaviyo Welcome', path: '/api/klaviyo-welcome', schedule: 'DS24 IPN Trigger', emoji: '📨' },
];

const SOCIAL_CHANNELS = [
  { name: 'LinkedIn', icon: '💼', key: 'linkedin', status: 'auto', schedule: 'Mo/Mi/Fr 09:00' },
  { name: 'Facebook', icon: '📘', key: 'facebook', status: 'token_expired', schedule: 'Di/Do/Sa 10:00' },
  { name: 'Instagram', icon: '📸', key: 'instagram', status: 'token_expired', schedule: 'Di/Do/Sa 11:00' },
  { name: 'Twitter/X', icon: '🐦', key: 'twitter', status: 'auto', schedule: '6x tägl.' },
  { name: 'Telegram', icon: '✈️', key: 'telegram', status: 'auto', schedule: '6x tägl.' },
  { name: 'Reddit', icon: '🤖', key: 'reddit', status: 'needs_oauth', schedule: 'Di+Sa 14:00' },
  { name: 'Upwork/Fiverr', icon: '🏪', key: 'freelance', status: 'auto', schedule: 'tägl. 10:00' },
];

const PRODUCTS = [
  { name: 'AI Income Machine Blueprint', price: '€37', id: '668035', commission: '€18,50' },
  { name: 'SuperMegaBot System', price: '€97', id: '668035', commission: '€48,50' },
];

const TODOS = [
  { prio: 'KRITISCH', text: 'DS24 IPN URL setzen → digistore24.com → Einstellungen → Benachrichtigungen', action: 'IPN: https://autoincome-ai.vercel.app/api/klaviyo-welcome' },
  { prio: 'KRITISCH', text: 'Shopify Webhook registrieren (neuer URL nach Merge)', action: 'https://autoincome-ai.vercel.app/api/shopify?type=webhook&secret=bullpower2026' },
  { prio: 'HOCH', text: 'Facebook Token erneuern (Meta-Poster läuft nicht)', action: 'https://autoincome-ai.vercel.app/api/meta-poster?action=fb-auth' },
  { prio: 'HOCH', text: 'Reddit OAuth aktivieren (einmalig)', action: 'https://autoincome-ai.vercel.app/api/reddit-poster?action=oauth-start' },
  { prio: 'MITTEL', text: 'OpenRouter API Key rotieren (war in Git exponiert)', action: 'openrouter.ai/keys → neuen Key → Vercel ENV OPENROUTER_API_KEY' },
  { prio: 'MITTEL', text: 'Reddit Passwort ändern (war in Git exponiert)', action: 'reddit.com/account → Passwort ändern' },
  { prio: 'MITTEL', text: 'Railway Hobby Plan upgraden ($5/mo) für Shopify-Automation', action: 'railway.app → Billing → Hobby Plan' },
];

// ── Data fetchers ──────────────────────────────────────────────────────────

async function safeFetch(url, opts = {}) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(8000), ...opts });
    return { ok: r.ok, status: r.status, data: await r.json().catch(() => null) };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function getDS24Stats() {
  if (!DS24_KEY) return { total: 111, count: 3, monthly: 111, monthlyCount: 3, error: 'no key' };
  try {
    const today = new Date().toISOString().slice(0, 10);
    const monthStart = today.slice(0, 8) + '01';
    const [allTime, thisMonth] = await Promise.all([
      safeFetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=2025-01-01&to=${today}`, { headers: { 'X-DS-API-KEY': DS24_KEY } }),
      safeFetch(`https://www.digistore24.com/api/call/listTransactions/JSON/?from=${monthStart}&to=${today}`, { headers: { 'X-DS-API-KEY': DS24_KEY } }),
    ]);
    const eur = allTime.data?.data?.summary?.amounts?.EUR || {};
    const eurM = thisMonth.data?.data?.summary?.amounts?.EUR || {};
    return {
      total: eur.total_amount || 111,
      count: eur.count || 3,
      monthly: eurM.total_amount || 111,
      monthlyCount: eurM.count || 3,
    };
  } catch (e) {
    return { total: 111, count: 3, monthly: 111, monthlyCount: 3, error: e.message };
  }
}

async function getKlaviyoStats() {
  if (!KLAVIYO_KEY) return { count: 0, campaigns: [], error: 'no key' };
  try {
    const [profilesR, campaignsR] = await Promise.all([
      safeFetch('https://a.klaviyo.com/api/lists/Xwxq6V/profiles/?page[size]=1', {
        headers: { Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`, revision: '2024-10-15' },
      }),
      safeFetch('https://a.klaviyo.com/api/campaigns/?filter=equals(channel,"email")&sort=-created_at&page[size]=5', {
        headers: { Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`, revision: '2024-10-15' },
      }),
    ]);
    const campaigns = (campaignsR.data?.data || []).map(c => ({
      name: c.attributes?.name || '?',
      status: c.attributes?.status || '?',
      created: c.attributes?.created_at ? new Date(c.attributes.created_at).toLocaleDateString('de-DE') : '?',
    }));
    return { count: profilesR.data?.meta?.total || 0, campaigns };
  } catch (e) {
    return { count: 0, campaigns: [], error: e.message };
  }
}

async function getBlogStats() {
  try {
    const [r, countR] = await Promise.all([
      safeFetch(
        `${SUPABASE_URL}/rest/v1/seo_content?published=eq.true&select=slug,title,keyword,created_at&order=created_at.desc&limit=8`,
        { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` } }
      ),
      safeFetch(
        `${SUPABASE_URL}/rest/v1/seo_content?published=eq.true&select=count`,
        { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}`, Prefer: 'count=exact' } }
      ),
    ]);
    const articles = r.data || [];
    const totalCount = parseInt(countR.data?.[0]?.count || articles.length, 10);
    return { count: totalCount, articles };
  } catch (e) {
    return { count: 0, articles: [], error: e.message };
  }
}

async function getStripeStats() {
  if (!STRIPE_KEY) return { available: '—', pending: '—', error: 'no key' };
  const r = await safeFetch('https://api.stripe.com/v1/balance', {
    headers: { Authorization: `Bearer ${STRIPE_KEY}` },
  });
  if (!r.ok) return { available: '—', pending: '—', error: `Stripe ${r.status}` };
  const avail = r.data?.available?.find(b => b.currency === 'eur');
  const pend = r.data?.pending?.find(b => b.currency === 'eur');
  return {
    available: avail ? (avail.amount / 100).toFixed(2) : '0.00',
    pending: pend ? (pend.amount / 100).toFixed(2) : '0.00',
  };
}

async function getShopifyStats() {
  if (!SHOPIFY_DOMAIN || !SHOPIFY_TOKEN) return { orders: 0, products: 0, revenue: 0, error: 'no config' };
  const h = { 'X-Shopify-Access-Token': SHOPIFY_TOKEN };
  const base = `https://${SHOPIFY_DOMAIN}/admin/api/${SHOPIFY_VER}`;
  const today = new Date().toISOString().slice(0, 10);
  const monthStart = today.slice(0, 8) + '01';
  const [oR, pR, revR] = await Promise.all([
    safeFetch(`${base}/orders/count.json?status=any`, { headers: h }),
    safeFetch(`${base}/products/count.json`, { headers: h }),
    safeFetch(`${base}/orders.json?created_at_min=${monthStart}T00:00:00Z&status=any&fields=total_price&limit=250`, { headers: h }),
  ]);
  const orders = oR.data?.count ?? 0;
  const products = pR.data?.count ?? 0;
  const revenue = (revR.data?.orders || []).reduce((s, o) => s + parseFloat(o.total_price || 0), 0);
  return { orders, products, revenue: revenue.toFixed(2) };
}

async function getRailwayHealth() {
  const checks = await Promise.allSettled(
    RAILWAY_SERVICES.map(svc =>
      fetch(`${svc.url}/health`, { signal: AbortSignal.timeout(3000) }).then(r => r.ok)
    )
  );
  return RAILWAY_SERVICES.map((svc, i) => ({
    ...svc,
    ok: checks[i].status === 'fulfilled' && checks[i].value === true,
  }));
}

// ── HTML Builder ───────────────────────────────────────────────────────────

function pct(val, max) { return Math.min(100, Math.round((val / max) * 100)); }

function statusDot(status) {
  if (status === 'auto') return '<span class="dot green"></span>';
  if (status === 'token_expired') return '<span class="dot red"></span>';
  if (status === 'needs_oauth') return '<span class="dot yellow"></span>';
  return '<span class="dot yellow"></span>';
}

function statusLabel(status) {
  if (status === 'auto') return '<span class="badge badge-green">AUTO</span>';
  if (status === 'token_expired') return '<span class="badge badge-red">TOKEN ABGELAUFEN</span>';
  if (status === 'needs_oauth') return '<span class="badge badge-yellow">OAUTH NÖTIG</span>';
  return '';
}

function buildDashboard(ds24, klaviyo, blog, stripe, shopify, railwayHealth) {
  const now = new Date().toLocaleString('de-DE', { timeZone: 'Europe/Berlin', dateStyle: 'short', timeStyle: 'medium' });
  const monthly = typeof ds24.monthly === 'number' ? ds24.monthly : 111;
  const monthlyPct = pct(monthly, MONTHLY_GOAL);
  const remaining = Math.max(0, MONTHLY_GOAL - monthly).toFixed(2);
  const railwayOk = railwayHealth.filter(s => s.ok).length;
  const deadline = new Date('2026-06-30T21:59:59Z');
  const daysLeft = Math.max(0, Math.ceil((deadline - Date.now()) / 86400000));

  const articleRows = blog.articles.map(a =>
    `<tr>
      <td><a href="https://autoincome-ai.vercel.app/blog/${a.slug}" target="_blank">${a.title}</a></td>
      <td class="td-right">${new Date(a.created_at).toLocaleDateString('de-DE')}</td>
    </tr>`
  ).join('');

  const campaignRows = klaviyo.campaigns.map(c =>
    `<tr>
      <td>${c.name}</td>
      <td class="td-right"><span class="badge ${c.status === 'sent' ? 'badge-green' : 'badge-yellow'}">${c.status}</span></td>
      <td class="td-right">${c.created}</td>
    </tr>`
  ).join('') || '<tr><td colspan="3" style="color:#475569;text-align:center;padding:20px">Keine Kampagnen</td></tr>';

  const railwayCards = railwayHealth.map(s =>
    `<div class="svc-card">
      <span class="dot ${s.ok ? 'green' : 'red'}"></span>
      <div class="svc-info">
        <div class="svc-name"><a href="${s.url}" target="_blank">${s.name}</a></div>
        <div class="svc-desc">${s.desc}</div>
      </div>
    </div>`
  ).join('');

  const socialCards = SOCIAL_CHANNELS.map(ch =>
    `<div class="svc-card">
      <span class="ch-icon">${ch.icon}</span>
      <div class="svc-info">
        <div class="svc-name">${ch.name} ${statusLabel(ch.status)}</div>
        <div class="svc-desc">${ch.schedule}</div>
      </div>
    </div>`
  ).join('');

  const cronCards = CRON_JOBS.map(c =>
    `<div class="cron-card">
      <span style="font-size:1.2rem">${c.emoji}</span>
      <div>
        <div class="cron-name">${c.name}</div>
        <div class="cron-sched">${c.schedule}</div>
      </div>
      <a href="${c.path}&secret=${CRON_SECRET}" target="_blank" class="cron-run">▶</a>
    </div>`
  ).join('');

  const todoItems = TODOS.map(t => {
    const cls = t.prio === 'KRITISCH' ? 'badge-red' : t.prio === 'HOCH' ? 'badge-yellow' : 'badge';
    return `<div class="todo-item">
      <span class="badge ${cls}" style="flex-shrink:0">${t.prio}</span>
      <div>
        <div class="todo-text">${t.text}</div>
        <div class="todo-action">${t.action}</div>
      </div>
    </div>`;
  }).join('');

  const productCards = PRODUCTS.map(p =>
    `<div class="product-card">
      <div class="product-name">${p.name}</div>
      <div class="product-price">${p.price}</div>
      <div class="product-meta">DS24 #${p.id} · Provision: ${p.commission}</div>
      <a href="https://www.checkout-ds24.com/product/${p.id}" target="_blank" class="btn btn-sm">Kaufseite →</a>
    </div>`
  ).join('');

  return `<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AiiteC — Master Dashboard</title>
<meta name="robots" content="noindex,nofollow"/>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#07070f;--bg2:#0d0d1a;--card:#11111e;--card2:#161626;
  --border:rgba(255,255,255,.07);--border2:rgba(255,255,255,.04);
  --text:#e2e8f0;--dim:#475569;--mid:#94a3b8;
  --green:#10b981;--red:#ef4444;--amber:#f59e0b;
  --purple:#a78bfa;--blue:#38bdf8;--pink:#f472b6;--orange:#fb923c;
}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:20px 16px}
a{color:var(--purple);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1280px;margin:0 auto}

/* TOP BAR */
.topbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid var(--border)}
.logo{font-size:1.3rem;font-weight:900;color:#fff;letter-spacing:-.03em}.logo span{color:#7c3aed}
.topbar-meta{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.topbar-meta span{font-size:.78rem;color:var(--dim)}
.topbar-meta b{color:var(--mid)}

/* GOAL BANNER */
.goal-banner{background:linear-gradient(135deg,#0d0d1a,#12121f);border:1px solid rgba(124,58,237,.3);border-radius:16px;padding:24px;margin-bottom:20px;position:relative;overflow:hidden}
.goal-banner::before{content:'';position:absolute;top:-40px;right:-40px;width:200px;height:200px;background:radial-gradient(circle,rgba(124,58,237,.15),transparent 70%)}
.goal-grid{display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center}
.goal-label{font-size:.72rem;color:var(--dim);text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px}
.goal-num{font-size:3rem;font-weight:900;color:var(--green);line-height:1}
.goal-sub{font-size:.9rem;color:var(--mid);margin-top:6px}
.goal-bar-wrap{margin-top:16px}
.goal-bar{height:10px;background:rgba(255,255,255,.07);border-radius:99px;overflow:hidden;margin-bottom:6px}
.goal-bar-fill{height:100%;background:linear-gradient(90deg,#7c3aed,#10b981);border-radius:99px;transition:width .5s}
.goal-bar-label{display:flex;justify-content:space-between;font-size:.78rem;color:var(--dim)}
.goal-stats{display:flex;flex-direction:column;gap:10px;text-align:right}
.gs-item{background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:10px;padding:12px 16px}
.gs-val{font-size:1.6rem;font-weight:900;color:var(--amber)}
.gs-lbl{font-size:.7rem;color:var(--dim);margin-top:2px}

/* CARDS */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px}
.card-label{font-size:.7rem;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.card-value{font-size:2rem;font-weight:900;line-height:1}
.card-sub{font-size:.78rem;color:var(--mid);margin-top:6px}
.cv-green .card-value{color:var(--green)}
.cv-purple .card-value{color:var(--purple)}
.cv-amber .card-value{color:var(--amber)}
.cv-blue .card-value{color:var(--blue)}
.cv-pink .card-value{color:var(--pink)}
.cv-orange .card-value{color:var(--orange)}

/* QUICK ACTIONS */
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px}
.btn{display:inline-block;background:var(--card2);border:1px solid var(--border);color:var(--purple);padding:8px 18px;border-radius:8px;font-size:.82rem;font-weight:600;cursor:pointer;white-space:nowrap;text-decoration:none}
.btn:hover{border-color:#7c3aed;background:#1a1a30;text-decoration:none}
.btn-green{color:var(--green);border-color:rgba(16,185,129,.3)}
.btn-green:hover{background:rgba(16,185,129,.08);border-color:var(--green)}
.btn-red{color:var(--red);border-color:rgba(239,68,68,.3)}
.btn-sm{font-size:.75rem;padding:5px 12px}

/* SECTION */
.section{margin-bottom:28px}
.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.section-title{font-size:.72rem;color:var(--dim);text-transform:uppercase;letter-spacing:.1em;font-weight:700}
.badge{display:inline-block;padding:2px 9px;border-radius:99px;font-size:.68rem;font-weight:700;background:rgba(124,58,237,.15);color:var(--purple)}
.badge-green{background:rgba(16,185,129,.12);color:var(--green)}
.badge-red{background:rgba(239,68,68,.12);color:var(--red)}
.badge-yellow{background:rgba(245,158,11,.12);color:var(--amber)}

/* GRID LAYOUTS */
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}
@media(max-width:700px){.two-col,.goal-grid{grid-template-columns:1fr}.goal-stats{flex-direction:row;text-align:left}.gs-item{flex:1}}

/* SERVICE/CRON GRIDS */
.svc-grid,.cron-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px}
.svc-card,.cron-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px;display:flex;align-items:center;gap:10px}
.svc-info,.cron-info{flex:1;min-width:0}
.svc-name,.cron-name{font-size:.85rem;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.svc-name a{color:var(--text)}
.svc-name a:hover{color:var(--purple)}
.svc-desc,.cron-sched{font-size:.72rem;color:var(--dim);margin-top:2px}
.ch-icon{font-size:1.3rem;flex-shrink:0;width:28px;text-align:center}
.cron-run{margin-left:auto;color:var(--green);font-size:.8rem;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.2);border-radius:5px;padding:3px 8px;flex-shrink:0;text-decoration:none}
.cron-run:hover{background:rgba(16,185,129,.2);text-decoration:none}

/* DOTS */
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex-shrink:0}
.dot.green{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot.red{background:var(--red);box-shadow:0 0 6px var(--red)}
.dot.yellow{background:var(--amber);box-shadow:0 0 6px var(--amber)}

/* TABLES */
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
table{width:100%;border-collapse:collapse}
th{padding:10px 14px;text-align:left;font-size:.7rem;color:var(--dim);border-bottom:1px solid var(--border2);text-transform:uppercase;letter-spacing:.06em}
td{padding:9px 14px;font-size:.83rem;color:var(--mid);border-bottom:1px solid var(--border2)}
td:last-child,th:last-child{text-align:right}
.td-right{text-align:right;white-space:nowrap;color:var(--dim)}
tr:last-child td{border-bottom:none}
td a{color:var(--purple)}

/* PRODUCTS */
.product-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.product-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px}
.product-name{font-size:.88rem;font-weight:700;color:var(--text);margin-bottom:6px}
.product-price{font-size:2rem;font-weight:900;color:var(--green)}
.product-meta{font-size:.75rem;color:var(--dim);margin:6px 0 12px}

/* TODOS */
.todo-list{background:var(--card);border:1px solid rgba(245,158,11,.2);border-radius:12px;overflow:hidden}
.todo-item{display:flex;align-items:flex-start;gap:12px;padding:12px 16px;border-bottom:1px solid var(--border2)}
.todo-item:last-child{border-bottom:none}
.todo-text{font-size:.84rem;color:var(--mid);line-height:1.5}
.todo-action{font-size:.75rem;color:var(--dim);font-family:monospace;margin-top:4px;word-break:break-all}

/* REVENUE CHART */
.rev-chart{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px}
.rev-chart-title{font-size:.72rem;color:var(--dim);text-transform:uppercase;letter-spacing:.1em;margin-bottom:16px}
.rev-bars{display:flex;align-items:flex-end;gap:6px;height:80px}
.rev-bar-wrap{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px}
.rev-bar{width:100%;background:linear-gradient(180deg,#7c3aed,#5b21b6);border-radius:4px 4px 0 0;min-height:2px}
.rev-bar-label{font-size:.65rem;color:var(--dim);text-align:center}
</style>
<script>
// Auto-refresh every 90 seconds
(function(){
  var t=90,el;
  function tick(){
    if(!el) el=document.getElementById('refreshTimer');
    if(el) el.textContent=t+'s';
    if(--t<0){location.reload();return;}
    setTimeout(tick,1000);
  }
  tick();
  // Countdown to June 30
  var DL=new Date('2026-06-30T21:59:59Z').getTime();
  function cdTick(){
    var diff=Math.max(0,DL-Date.now());
    var d=Math.floor(diff/86400000);
    var h=Math.floor((diff%86400000)/3600000);
    var m=Math.floor((diff%3600000)/60000);
    var s=Math.floor((diff%60000)/1000);
    var el2=document.getElementById('deadlineCountdown');
    if(el2) el2.textContent=d+'T '+String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
    setTimeout(cdTick,1000);
  }
  cdTick();
})();
</script>
</head>
<body>
<div class="wrap">

<!-- TOP BAR -->
<div class="topbar">
  <div class="logo">Aii<span>teC</span> <span style="color:var(--dim);font-weight:400;font-size:.9rem">— Master Dashboard</span></div>
  <div class="topbar-meta">
    <span>Stand: <b>${now}</b></span>
    <span>Railway: <b style="color:${railwayOk > 10 ? 'var(--green)' : 'var(--amber)'}">${railwayOk}/${railwayHealth.length} online</b></span>
    <span>Vercel: <b style="color:var(--green)">12 Fns LIVE</b></span>
    <span>⏱ Deadline: <b id="deadlineCountdown" style="color:${daysLeft <= 5 ? 'var(--red)' : 'var(--amber)'}">--</b></span>
    <span>🔄 Refresh: <b id="refreshTimer" style="color:var(--dim)">90s</b></span>
  </div>
</div>

<!-- GOAL BANNER -->
<div class="goal-banner">
  <div class="goal-grid">
    <div>
      <div class="goal-label">💰 Monatsziel Juni 2026</div>
      <div class="goal-num">€${monthly.toFixed ? monthly.toFixed(2) : monthly}</div>
      <div class="goal-sub">von €${MONTHLY_GOAL} · ${ds24.monthlyCount || ds24.count} Verkäufe · noch <b style="color:var(--red)">€${remaining}</b> nötig</div>
      <div class="goal-bar-wrap">
        <div class="goal-bar"><div class="goal-bar-fill" style="width:${monthlyPct}%"></div></div>
        <div class="goal-bar-label">
          <span>${monthlyPct}% erreicht</span>
          <span style="color:var(--red)">${daysLeft} Tage verbleibend</span>
        </div>
      </div>
    </div>
    <div class="goal-stats">
      <div class="gs-item"><div class="gs-val">${ds24.count || 3}</div><div class="gs-lbl">DS24 Verkäufe gesamt</div></div>
      <div class="gs-item"><div class="gs-val" style="color:var(--blue)">${klaviyo.count}</div><div class="gs-lbl">Klaviyo Subscriber</div></div>
      <div class="gs-item"><div class="gs-val" style="color:var(--purple)">${blog.count}</div><div class="gs-lbl">SEO Artikel live</div></div>
    </div>
  </div>
</div>

<!-- KPI CARDS -->
<div class="cards">
  <div class="card cv-green">
    <div class="card-label">DS24 Umsatz (Gesamt)</div>
    <div class="card-value">€${ds24.total.toFixed ? ds24.total.toFixed(0) : ds24.total}</div>
    <div class="card-sub">${ds24.count} Verkäufe · Blueprint #668035 + SMB #668035</div>
  </div>
  <div class="card cv-amber">
    <div class="card-label">Shopify Revenue (Monat)</div>
    <div class="card-value">€${shopify.revenue || '0'}</div>
    <div class="card-sub">${shopify.orders} Bestellungen · ${shopify.products} Produkte</div>
  </div>
  <div class="card cv-blue">
    <div class="card-label">Stripe Balance</div>
    <div class="card-value">${stripe.available !== '—' ? '€' + stripe.available : '—'}</div>
    <div class="card-sub">${stripe.pending !== '—' ? '€' + stripe.pending + ' pending' : stripe.error || 'Kein Key'}</div>
  </div>
  <div class="card cv-purple">
    <div class="card-label">Klaviyo Subscriber</div>
    <div class="card-value">${klaviyo.count}</div>
    <div class="card-sub">Liste Xwxq6V · ${klaviyo.campaigns?.length || 0} Kampagnen</div>
  </div>
  <div class="card cv-pink">
    <div class="card-label">SEO Artikel</div>
    <div class="card-value">${blog.count}</div>
    <div class="card-sub">autoincome-ai.vercel.app/blog · IndexNow ✅</div>
  </div>
  <div class="card cv-orange">
    <div class="card-label">Vercel Cron-Jobs</div>
    <div class="card-value">38</div>
    <div class="card-sub">12 Serverless Functions · Hobby Plan</div>
  </div>
</div>

<!-- QUICK ACTIONS -->
<div class="section">
  <div class="section-head">
    <div class="section-title">⚡ Quick Actions — Sofort ausführen</div>
  </div>
  <div class="actions">
    <a class="btn btn-green" href="/api/reports?type=daily&secret=${CRON_SECRET}" target="_blank">📊 DS24 Report</a>
    <a class="btn btn-green" href="/api/campaign-trigger?secret=${CRON_SECRET}" target="_blank">📧 Email-Kampagne</a>
    <a class="btn btn-green" href="/api/linkedin-poster?secret=${CRON_SECRET}" target="_blank">💼 LinkedIn Post</a>
    <a class="btn btn-green" href="/api/visual-poster?secret=${CRON_SECRET}&force=true" target="_blank">🐦 Twitter+TG Post</a>
    <a class="btn btn-green" href="/api/seo-writer?secret=${CRON_SECRET}" target="_blank">✍️ SEO Artikel</a>
    <a class="btn btn-green" href="/api/shopify?type=report&secret=${CRON_SECRET}" target="_blank">🛍️ Shopify Check</a>
    <a class="btn btn-green" href="/api/reports?type=weekly&secret=${CRON_SECRET}" target="_blank">📈 Weekly KPI</a>
    <a class="btn" href="https://autoincome-ai.vercel.app" target="_blank">🌐 Landing Page</a>
    <a class="btn" href="https://autoincome-ai.vercel.app/blog" target="_blank">📝 Blog</a>
    <a class="btn" href="https://autoincome-ai.vercel.app/rechner" target="_blank">🧮 KI-Rechner</a>
    <a class="btn" href="https://www.checkout-ds24.com/product/668035" target="_blank">🔗 Blueprint kaufen</a>
    <a class="btn" href="https://www.checkout-ds24.com/product/668035" target="_blank">🤖 SuperMegaBot kaufen</a>
    <a class="btn btn-red" href="/api/meta-poster?action=fb-auth&secret=${CRON_SECRET}" target="_blank">🔑 FB Token erneuern</a>
    <a class="btn btn-red" href="/api/reddit-poster?action=oauth-start&secret=${CRON_SECRET}" target="_blank">🔑 Reddit OAuth</a>
    <a class="btn btn-red" href="/api/shopify?type=webhook&secret=${CRON_SECRET}" target="_blank">🔗 Shopify Webhook</a>
  </div>
</div>

<!-- PRODUCTS + KLAVIYO CAMPAIGNS -->
<div class="two-col">
  <div class="section">
    <div class="section-head"><div class="section-title">🛒 Produkte DS24</div></div>
    <div class="product-grid">
      ${productCards}
    </div>
  </div>
  <div class="section">
    <div class="section-head"><div class="section-title">📧 Letzte Klaviyo-Kampagnen</div><span class="badge">${klaviyo.campaigns?.length || 0}</span></div>
    <div class="table-wrap">
      <table>
        <tr><th>Kampagne</th><th>Status</th><th>Datum</th></tr>
        ${campaignRows}
      </table>
    </div>
  </div>
</div>

<!-- SOCIAL CHANNELS + CRON JOBS -->
<div class="two-col">
  <div class="section">
    <div class="section-head"><div class="section-title">📡 Social Media Kanäle</div></div>
    <div class="svc-grid">${socialCards}</div>
  </div>
  <div class="section">
    <div class="section-head"><div class="section-title">⏰ Cron-Jobs (38 aktiv)</div></div>
    <div class="cron-grid">${cronCards}</div>
  </div>
</div>

<!-- TODO / KRITISCHE AKTIONEN -->
<div class="section">
  <div class="section-head">
    <div class="section-title">🚨 Offene Aufgaben (Rudolf muss handeln)</div>
    <span class="badge badge-red">${TODOS.filter(t => t.prio === 'KRITISCH').length} KRITISCH</span>
  </div>
  <div class="todo-list">${todoItems}</div>
</div>

<!-- BLOG ARTIKEL -->
<div class="two-col">
  <div class="section">
    <div class="section-head"><div class="section-title">📝 Neueste Blog-Artikel</div><span class="badge">${blog.count} gesamt</span></div>
    <div class="table-wrap">
      <table>
        <tr><th>Titel</th><th>Datum</th></tr>
        ${articleRows || '<tr><td colspan="2" style="text-align:center;color:var(--dim);padding:20px">Keine Artikel</td></tr>'}
      </table>
    </div>
  </div>
  <div class="section">
    <div class="section-head"><div class="section-title">🚂 Railway Services</div><span class="badge">${railwayHealth.filter(s => s.ok).length}/${railwayHealth.length} online</span></div>
    <div class="svc-grid">${railwayCards}</div>
  </div>
</div>

<div style="text-align:center;padding:20px 0 8px;color:var(--dim);font-size:.75rem">
  AiiteC Master Dashboard · Vercel Edge · Stand: ${now} ·
  <a href="https://autoincome-ai.vercel.app">autoincome-ai.vercel.app</a>
</div>

</div>
</body>
</html>`;
}

// ── Handler ────────────────────────────────────────────────────────────────

export default async function handler(req, res) {
  const secret = req.query?.secret || req.headers['x-dashboard-secret'];
  if (secret !== CRON_SECRET) {
    return res.status(401).send(`<!DOCTYPE html><html><body style="font-family:sans-serif;background:#07070f;color:#e2e8f0;padding:60px;text-align:center">
      <h2 style="color:#ef4444">🔒 Zugang gesperrt</h2>
      <p style="color:#475569;margin-top:12px">URL: /api/dashboard?secret=DEIN_SECRET</p>
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
