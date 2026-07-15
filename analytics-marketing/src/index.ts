import 'dotenv/config'
import path from 'path'
import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import { connectRedis } from './lib/redis'
import { httpRequestsTotal, httpRequestDuration } from './lib/metrics'
import healthRouter from './routes/health'
import analyticsRouter from './routes/analytics'
import marketingRouter from './routes/marketing'
import statsRouter from './routes/stats'
import billingRouter from './routes/billing'
const app = express()
const PORT = process.env.PORT || 3000
app.use(helmet({ contentSecurityPolicy: false }))
app.use(cors())
app.use(express.json())
app.use((req, _res, next) => {
  const end = httpRequestDuration.startTimer({ method: req.method, route: req.path, service: 'analytics-marketing-service' })
  _res.on('finish', () => {
    httpRequestsTotal.inc({ method: req.method, route: req.path, status: String(_res.statusCode), service: 'analytics-marketing-service' })
    end()
  })
  next()
})
// Serve landing page BEFORE API routes so it's not swallowed
app.use(express.static(path.join(__dirname, '..', 'public')))
// eslint-disable-next-line @typescript-eslint/no-explicit-any
app.get('/', (_req: any, res: any) => res.sendFile(path.join(__dirname, '..', 'public', 'index.html')))
app.use(healthRouter)
app.use(analyticsRouter)
app.use(marketingRouter)
app.use(statsRouter)
app.use(billingRouter)
app.post('/api/ingest', (req: any, res: any) => {
  try {
    const { title = '', url = '', keyword = '', product_name = '', product_url = '' } = req.body || {}
    const relevant = /analytics|marketing|klaviyo|mailchimp|email|pixel/i.test(keyword + ' ' + title)
    const prefix = relevant ? '🎯 <b>Relevanter SEO Artikel!</b>' : '📰 <b>SEO Artikel → Analytics Marketing Pro</b>'
    const token = process.env.TELEGRAM_BOT_TOKEN; const chat = process.env.TELEGRAM_CHAT_ID
    if (token && chat) {
      const https = require('https'); const body = JSON.stringify({ chat_id: chat, text: `${prefix}\n🔑 ${keyword}\n📄 ${title}\n🔗 ${url}\n🛒 ${product_name}: ${product_url}`, parse_mode: 'HTML' })
      const r = https.request({ hostname: 'api.telegram.org', path: `/bot${token}/sendMessage`, method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }); r.on('error', () => {}); r.write(body); r.end()
    }
    res.json({ status: 'ok', service: 'analytics-marketing-service', processed: title, relevant })
  } catch (e: any) { res.json({ error: e.message }) }
})
async function tgSend(text: string) {
  const token = process.env.TELEGRAM_BOT_TOKEN; const chat = process.env.TELEGRAM_CHAT_ID
  if (!token || !chat) return
  const https = require('https')
  const body = JSON.stringify({ chat_id: chat, text, parse_mode: 'HTML' })
  const r = https.request({ hostname: 'api.telegram.org', path: `/bot${token}/sendMessage`, method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } })
  r.on('error', () => {}); r.write(body); r.end()
}

async function dailyMarketingStats() {
  const axios = (await import('axios')).default
  const mcKey = process.env.MAILCHIMP_API_KEY; const mcPrefix = process.env.MAILCHIMP_SERVER_PREFIX; const mcList = process.env.MAILCHIMP_AUDIENCE_ID
  const klKey = process.env.KLAVIYO_API_KEY

  let mcCount: number | string = '?'
  let klLists: { id: string; name: string }[] = []

  if (mcKey && mcPrefix && mcList) {
    try {
      const r = await axios.get(`https://${mcPrefix}.api.mailchimp.com/3.0/lists/${mcList}`, { auth: { username: 'anystring', password: mcKey } })
      mcCount = r.data?.stats?.member_count ?? '?'
    } catch {}
  }
  if (klKey) {
    try {
      const r = await axios.get('https://a.klaviyo.com/api/lists/', { headers: { 'Authorization': `Klaviyo-API-Key ${klKey}`, 'revision': '2023-12-15' } })
      klLists = (r.data?.data || []).map((l: any) => ({ id: l.id, name: l.attributes?.name || l.id }))
    } catch {}
  }

  const klSummary = klLists.map(l => `  • ${l.name}`).join('\n') || '  (none)'
  await tgSend(`📊 <b>Analytics Marketing — Daily Stats</b>\n\n📧 Mailchimp Subscribers: <b>${mcCount}</b>\n📋 Klaviyo Lists:\n${klSummary}\n🕐 ${new Date().toISOString().slice(0,16)} UTC`)
  console.log('[scheduler] dailyMarketingStats sent')
}

function startAutonomousLoop() {
  const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY || '';
  const SEO_ENGINE = process.env.SEO_ENGINE_URL || 'https://seo-traffic-engine-production.up.railway.app';
  const APP_URL = process.env.APP_URL || 'https://analytics-marketing-service-production.up.railway.app';
  const topics = ['Email Marketing Strategie 2025','Klaviyo vs Mailchimp Vergleich','E-Mail Automatisierung Shopify','Newsletter Conversion optimieren','Marketing Analytics Dashboard'];
  let idx = 0; let cycle = 0;
  async function runCycle() {
    try {
      const topic = topics[idx++ % topics.length];
      if (ANTHROPIC_KEY) {
        const https = require('https');
        await new Promise<void>((resolve) => {
          const body = JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 500,
            messages: [{ role: 'user', content: `100-Wort SEO-Artikel Deutsch über: ${topic}. Nur Text.` }] });
          const req = https.request({ hostname: 'api.anthropic.com', path: '/v1/messages', method: 'POST',
            headers: { 'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } },
            (res: any) => {
              let data = '';
              res.on('data', (c: string) => data += c);
              res.on('end', async () => {
                try {
                  const d = JSON.parse(data);
                  const content: string = d.content?.[0]?.text || '';
                  const ingestBody = JSON.stringify({ title: `${topic} — Analytics Marketing`, content, keyword: topic, source: 'analytics-marketing-service' });
                  const ingestReq = https.request({ hostname: new URL(SEO_ENGINE).hostname, path: '/api/ingest', method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(ingestBody) } });
                  ingestReq.on('error', () => {}); ingestReq.write(ingestBody); ingestReq.end();
                  await tgSend(`📊 <b>Analytics Marketing SEO</b>\n\n<b>${topic}</b>\n\n${content.substring(0, 280)}...\n\n🌐 ${APP_URL}`);
                  console.log(`[Analytics] Auto-Content: ${topic}`);
                } catch {}
                resolve();
              });
            });
          req.on('error', () => resolve()); req.write(body); req.end();
        });
      }
      // Ping Google + Bing for all project sitemaps every cycle
      const https2 = require('https');
      const sitemaps = [
        `${APP_URL}/sitemap.xml`,
        'https://shopify-automaton-suite-production-e405.up.railway.app/sitemap.xml',
        'https://seo-turbo-tools-production.up.railway.app/sitemap.xml',
        'https://bullpower-hub-portal.netlify.app/sitemap.xml',
      ];
      for (const sm of sitemaps) {
        const enc = encodeURIComponent(sm);
        const g = https2.request({ hostname: 'www.google.com', path: `/ping?sitemap=${enc}`, method: 'GET' });
        g.on('error', () => {}); g.end();
        const b = https2.request({ hostname: 'www.bing.com', path: `/ping?sitemap=${enc}`, method: 'GET' });
        b.on('error', () => {}); b.end();
      }
      cycle++;
    } catch (e: any) { console.error('[Analytics] loop error:', e.message); }
  }
  setTimeout(runCycle, 70000);
  setInterval(runCycle, 6 * 60 * 60 * 1000);
  console.log('[Analytics] Autonomous SEO loop gestartet (alle 6h)');
}

// ── MAXIMUM TUNING v2.0 — Google Trends + IndexNow + /api/trends + /stats ───
const _analyticsState = { trendingTopics: [] as string[], lastTrendFetch: 0, indexnowPings: 0 };

async function fetchGoogleTrends(geo = 'DE'): Promise<string[]> {
  if (Date.now() - _analyticsState.lastTrendFetch < 7_200_000) return _analyticsState.trendingTopics;
  try {
    const https = require('https');
    const xml: string = await new Promise((resolve, reject) => {
      const r = https.get({ hostname: 'trends.google.com', path: `/trends/trendingsearches/daily/rss?geo=${geo}`, headers: { 'User-Agent': 'Mozilla/5.0' } }, (res: any) => { let d = ''; res.on('data', (c: any) => d += c); res.on('end', () => resolve(d)); });
      r.on('error', reject); r.setTimeout(12000, () => { r.destroy(); reject(new Error('timeout')); });
    });
    const matches = xml.matchAll(/<title><!\[CDATA\[(.*?)\]\]><\/title>|<title>(.*?)<\/title>/g);
    const kws: string[] = [];
    for (const m of matches) { const kw = (m[1] || m[2] || '').trim().toLowerCase(); if (kw && kw !== 'google trends') kws.push(kw); }
    if (kws.length) { _analyticsState.trendingTopics = kws.slice(0, 15); _analyticsState.lastTrendFetch = Date.now(); }
    console.log(`[Trends] Fetched ${kws.length} keywords`);
  } catch (e: any) { console.warn('[Trends] error:', e.message); }
  return _analyticsState.trendingTopics;
}

function indexNowPing(urls: string[]): void {
  const APP_URL = process.env.APP_URL || 'https://analytics-marketing-service-production.up.railway.app';
  const key = process.env.INDEXNOW_KEY || 'analyticsmarketing2026turbo';
  const host = APP_URL.replace(/^https?:\/\//, '');
  const payload = JSON.stringify({ host, key, keyLocation: `${APP_URL}/${key}.txt`, urlList: urls.slice(0, 50) });
  const https = require('https');
  for (const ep of ['api.indexnow.org', 'www.bing.com']) {
    const r = https.request({ hostname: ep, path: '/indexnow', method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(payload) } });
    r.on('error', () => {}); r.write(payload); r.end();
  }
  _analyticsState.indexnowPings++;
}

// /api/trends — returns current trending keywords
app.get('/api/trends', async (_req: any, res: any) => {
  const topics = await fetchGoogleTrends('DE');
  res.json({ status: 'ok', trending: topics, count: topics.length, last_fetch: _analyticsState.lastTrendFetch ? new Date(_analyticsState.lastTrendFetch).toISOString() : null });
});
app.post('/api/trends', async (_req: any, res: any) => {
  _analyticsState.lastTrendFetch = 0; // force refresh
  const topics = await fetchGoogleTrends('DE');
  res.json({ status: 'ok', trending: topics, count: topics.length, refreshed: true });
});

// /api/indexnow — bulk ping endpoint
app.post('/api/indexnow', (req: any, res: any) => {
  const urls: string[] = Array.isArray(req.body?.urls) ? req.body.urls : [process.env.APP_URL || ''];
  indexNowPing(urls);
  res.json({ status: 'ok', urls_submitted: urls.length, pings: _analyticsState.indexnowPings });
});

// IndexNow key verification file
app.get(`/${process.env.INDEXNOW_KEY || 'analyticsmarketing2026turbo'}.txt`, (_req: any, res: any) => {
  res.type('text/plain').send(process.env.INDEXNOW_KEY || 'analyticsmarketing2026turbo');
});

// /stats — turbo stats
app.get('/api/stats-turbo', (_req: any, res: any) => {
  res.json({
    service: 'analytics-marketing-service',
    version: '2.0-TURBO',
    trending_topics: _analyticsState.trendingTopics.slice(0, 10),
    last_trends_fetch: _analyticsState.lastTrendFetch ? new Date(_analyticsState.lastTrendFetch).toISOString() : null,
    indexnow_pings: _analyticsState.indexnowPings,
    uptime: process.uptime(),
  });
});

async function autonomousTrendingContent() {
  const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY || '';
  const APP_URL = process.env.APP_URL || 'https://analytics-marketing-service-production.up.railway.app';
  const SEO_ENGINE = process.env.SEO_ENGINE_URL || 'https://seo-traffic-engine-production.up.railway.app';
  if (!ANTHROPIC_KEY) return;
  const topics = await fetchGoogleTrends('DE');
  const top5 = topics.slice(0, 5);
  if (!top5.length) return;
  try {
    const https = require('https');
    const body = JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 600,
      messages: [{ role: 'user', content: `Erstelle für diese 5 Trending Topics jeweils eine E-Mail Betreffzeile + 2 Sätze Ad-Copy auf Deutsch:\n${top5.map((t,i) => `${i+1}. ${t}`).join('\n')}\nFormat: [Thema] | Betreff: ... | Ad: ...` }] });
    await new Promise<void>((resolve) => {
      const onResponse = async (res: any) => {
        let d = '';
        res.on('data', (c: any) => { d += c; });
        res.on('end', async () => {
          try {
            const parsed = JSON.parse(d);
            const content: string = parsed.content?.[0]?.text || '';
            await tgSend(`📈 <b>Analytics TURBO — Trending Content</b>\n\n<b>Top Trends:</b>\n${top5.slice(0,3).map((t: string) => `• ${t}`).join('\n')}\n\n<b>AI Ad-Copy:</b>\n${content.substring(0, 600)}\n\n🌐 ${APP_URL}`);
            const ingestBody = JSON.stringify({ title: `Marketing Trends: ${top5[0]}`, keyword: top5[0], content, source: 'analytics-marketing', url: APP_URL });
            const ir = https.request({ hostname: new URL(SEO_ENGINE).hostname, path: '/api/ingest', method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(ingestBody) } });
            ir.on('error', () => {}); ir.write(ingestBody); ir.end();
          } catch { /* ignore */ }
          resolve();
        });
      };
      const r = https.request({ hostname: 'api.anthropic.com', path: '/v1/messages', method: 'POST',
        headers: { 'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, onResponse);
      r.on('error', () => resolve()); r.write(body); r.end();
    });
    // IndexNow ping
    indexNowPing([APP_URL]);
    console.log('[Analytics TURBO] Trending content cycle done');
  } catch (e: any) { console.error('[Analytics TURBO] error:', e.message); }
}

async function start() {
  await connectRedis().catch(err => console.warn('Redis init warning:', (err as Error).message));
  app.listen(PORT, () => {
    console.log(`analytics-marketing-service TURBO v2.0 running on port ${PORT}`)
    setTimeout(() => {
      dailyMarketingStats().catch(console.error)
      setInterval(() => dailyMarketingStats().catch(console.error), 24 * 60 * 60 * 1000)
    }, 3 * 60 * 1000)
    startAutonomousLoop(); // still runs for SEO ingest
    // TURBO: autonomous trending content every 3h
    setTimeout(() => {
      fetchGoogleTrends('DE').catch(console.error);
      autonomousTrendingContent().catch(console.error);
      setInterval(() => autonomousTrendingContent().catch(console.error), 3 * 60 * 60 * 1000);
      setInterval(() => fetchGoogleTrends('DE'), 2 * 60 * 60 * 1000);
    }, 90000);
  });
}
start()
