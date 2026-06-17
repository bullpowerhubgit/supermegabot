#!/usr/bin/env node
require('dotenv').config();

const tests = [
  { name: 'GitHub', url: 'https://api.github.com/user', headers: { 'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`, 'User-Agent': 'Rudibot' } },
  { name: 'Claude', url: 'https://api.anthropic.com/v1/messages', method: 'POST', headers: { 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json' }, body: { model: 'claude-sonnet-4-20250514', max_tokens: 10, messages: [{ role: 'user', content: 'Hi' }] } },
  { name: 'Perplexity', url: 'https://api.perplexity.ai/chat/completions', method: 'POST', headers: { 'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`, 'Content-Type': 'application/json' }, body: { model: 'sonar', messages: [{ role: 'user', content: 'Hi' }], max_tokens: 10 } },
  { name: 'Supabase', url: `${process.env.SUPABASE_URL}/rest/v1/`, headers: { 'apikey': process.env.SUPABASE_ANON_KEY, 'Authorization': `Bearer ${process.env.SUPABASE_ANON_KEY}` } },
  { name: 'Stripe', url: 'https://api.stripe.com/v1/account', headers: { 'Authorization': `Bearer ${process.env.STRIPE_API_KEY}` } },
  { name: 'Shopify', url: `https://${process.env.SHOPIFY_STORE_URL}/admin/api/2025-01/shop.json`, headers: { 'X-Shopify-Access-Token': process.env.SHOPIFY_ADMIN_TOKEN } },
  { name: 'Printify', url: 'https://api.printify.com/v1/shops.json', headers: { 'Authorization': `Bearer ${process.env.PRINTIFY_API_KEY}` } },
  { name: 'Telegram', url: `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/getMe` },
  { name: 'YouTube', url: `https://www.googleapis.com/youtube/v3/channels?part=snippet&id=${process.env.YOUTUBE_CHANNEL_ID}&key=${process.env.YOUTUBE_API_KEY}` },
  { name: 'Google AI', url: `https://generativelanguage.googleapis.com/v1/models?key=${process.env.GOOGLE_AI_API_KEY}` },
  { name: 'Mailchimp', url: `https://${process.env.MAILCHIMP_SERVER_PREFIX}.api.mailchimp.com/3.0/ping`, headers: { 'Authorization': `Bearer ${process.env.MAILCHIMP_API_KEY}` } },
  { name: 'OpenAI', url: 'https://api.openai.com/v1/models', headers: { 'Authorization': `Bearer ${process.env.OPENAI_API_KEY}` } },
];

async function run() {
  console.log('═══════════════════════════════════════════');
  console.log('  RUDIBOT API TEST REPORT');
  console.log('═══════════════════════════════════════════\n');
  for (const t of tests) {
    try {
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), 10000);
      const opts = { method: t.method || 'GET', headers: t.headers || {}, signal: ctrl.signal };
      if (t.body) opts.body = JSON.stringify(t.body);
      const res = await fetch(t.url, opts);
      clearTimeout(to);
      const data = await res.json().catch(() => null);
      const ok = res.ok && (t.name === 'Telegram' ? data?.ok : true);
      const icon = ok ? '✅' : '❌';
      const status = ok ? 'OK' : `FAIL (${res.status})`;
      let detail = '';
      if (t.name === 'GitHub' && data?.login) detail = `User: ${data.login}`;
      else if (t.name === 'Shopify' && data?.shop?.name) detail = `Store: ${data.shop.name}`;
      else if (t.name === 'Printify' && data?.data) detail = `Shops: ${data.data.length}`;
      else if (t.name === 'Telegram' && data?.result?.username) detail = `@${data.result.username}`;
      else if (t.name === 'Stripe' && data?.id) detail = `Account: ${data.id}`;
      else if (!ok && data?.error?.message) detail = data.error.message.slice(0, 60);
      else if (!ok && data?.detail) detail = data.detail.slice(0, 60);
      else if (!ok && data?.description) detail = data.description.slice(0, 60);
      console.log(`${icon} ${t.name.padEnd(12)} | ${status.padEnd(12)} | ${detail}`);
    } catch (e) {
      console.log(`❌ ${t.name.padEnd(12)} | ERROR        | ${e.message.slice(0, 50)}`);
    }
  }
  console.log('\n═══════════════════════════════════════════');
}
run();
