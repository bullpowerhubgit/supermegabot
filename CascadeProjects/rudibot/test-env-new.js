#!/usr/bin/env node
// Test APIs directly using .env.new
require('dotenv').config({ path: '/Users/rudolfsarkany/CascadeProjects/rudibot/.env.new' });

const c = {
  g: '\x1b[32m', r: '\x1b[31m', y: '\x1b[33m', b: '\x1b[34m', x: '\x1b[0m'
};

function log(ok, name, msg) {
  const col = ok ? c.g : c.r;
  console.log(`${col}${ok ? '✅' : '❌'} ${name.padEnd(14)}${c.x} ${msg}`);
}

async function test(name, url, opts, check) {
  try {
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    const ok = check ? check(res, data) : res.ok;
    log(ok, name, ok ? 'OK' : (data.error?.message || data.message || data.description || `HTTP ${res.status}`));
    return ok;
  } catch(e) {
    log(false, name, e.message);
    return false;
  }
}

async function main() {
  console.log(`${c.b}═══════════════════════════════════════════════════════${c.x}`);
  console.log(`${c.b}  API TEST mit .env.new${c.x}`);
  console.log(`${c.b}═══════════════════════════════════════════════════════${c.x}\n`);

  let passed = 0, total = 0;

  // 1. Anthropic
  total++;
  if (await test('Anthropic', 'https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'x-api-key': process.env.ANTHROPIC_API_KEY, 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({ model: 'claude-sonnet-4-20250514', max_tokens: 5, messages: [{role:'user',content:'Hi'}] })
  }, (res, data) => res.ok && !!data.content)) passed++;

  // 2. OpenAI
  total++;
  if (await test('OpenAI', 'https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'gpt-4o-mini', max_tokens: 5, messages: [{role:'user',content:'Hi'}] })
  }, (res, data) => res.ok && !!data.choices)) passed++;

  // 3. Perplexity
  total++;
  if (await test('Perplexity', 'https://api.perplexity.ai/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'sonar-pro', messages: [{role:'user',content:'Hi'}] })
  }, (res, data) => res.ok && !!data.choices)) passed++;

  // 4. GitHub
  total++;
  if (await test('GitHub', 'https://api.github.com/user', {
    headers: { 'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`, 'User-Agent': 'RudiBot' }
  }, (res, data) => res.ok && !!data.login)) passed++;

  // 5. Telegram
  total++;
  if (await test('Telegram', `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/getMe`, {},
  (res, data) => res.ok && data.ok && !!data.result)) passed++;

  // 6. Shopify
  total++;
  if (process.env.SHOPIFY_ADMIN_TOKEN) {
    if (await test('Shopify', `https://${process.env.SHOPIFY_STORE_URL}/admin/api/2025-01/shop.json`, {
      headers: { 'X-Shopify-Access-Token': process.env.SHOPIFY_ADMIN_TOKEN }
    }, (res, data) => res.ok && !!data.shop)) passed++;
  } else { log(false, 'Shopify', 'Key fehlt'); }

  // 7. Stripe
  total++;
  if (await test('Stripe', 'https://api.stripe.com/v1/account', {
    headers: { 'Authorization': `Bearer ${process.env.STRIPE_API_KEY}` }
  }, (res, data) => res.ok || data.id)) passed++;

  // 8. Supabase
  total++;
  if (await test('Supabase', `${process.env.SUPABASE_URL}/rest/v1/`, {
    headers: { 'apikey': process.env.SUPABASE_ANON_KEY, 'Authorization': `Bearer ${process.env.SUPABASE_ANON_KEY}` }
  }, (res) => res.ok || res.status === 400)) passed++;

  // 9. Printify
  total++;
  if (await test('Printify', 'https://api.printify.com/v1/shops.json', {
    headers: { 'Authorization': `Bearer ${process.env.PRINTIFY_API_KEY}` }
  }, (res, data) => res.ok && Array.isArray(data.data))) passed++;

  // 10. Klaviyo
  total++;
  if (await test('Klaviyo', 'https://a.klaviyo.com/api/profiles/', {
    headers: { 'Authorization': `Klaviyo-API-Key ${process.env.KLAVIYO_API_KEY}`, 'revision': '2023-02-22' }
  }, (res, data) => res.ok || Array.isArray(data.data))) passed++;

  // 11. Mailchimp
  total++;
  const dc = (process.env.MAILCHIMP_API_KEY || '').split('-')[1] || process.env.MAILCHIMP_SERVER_PREFIX;
  if (dc) {
    if (await test('Mailchimp', `https://${dc}.api.mailchimp.com/3.0/lists`, {
      headers: { 'Authorization': `Bearer ${process.env.MAILCHIMP_API_KEY}` }
    }, (res, data) => res.ok || Array.isArray(data.lists))) passed++;
  } else { log(false, 'Mailchimp', 'Key fehlt'); }

  // 12. YouTube
  total++;
  if (await test('YouTube', `https://www.googleapis.com/youtube/v3/channels?part=snippet&id=${process.env.YOUTUBE_CHANNEL_ID}&key=${process.env.YOUTUBE_API_KEY}`, {},
  (res, data) => res.ok && !!data.items)) passed++;

  // 13. Google AI
  total++;
  if (await test('Google AI', `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${process.env.GOOGLE_AI_API_KEY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents: [{ parts: [{ text: 'Hi' }] }] })
  }, (res, data) => res.ok && !!data.candidates)) passed++;

  console.log(`\n${c.b}═══════════════════════════════════════════════════════${c.x}`);
  console.log(`  Ergebnis: ${c.g}${passed}/${total}${c.x} APIs funktionieren`);
  console.log(`${c.b}═══════════════════════════════════════════════════════${c.x}\n`);
}

main().catch(console.error);
