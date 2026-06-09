#!/usr/bin/env node
/**
 * Comprehensive API Test Script
 * Tests each API individually and reports status
 */
require('dotenv').config();

const results = [];

function log(category, status, message) {
  const icon = status === 'OK' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`${icon} ${category.padEnd(20)} | ${status.padEnd(6)} | ${message}`);
  results.push({ category, status, message });
}

async function testAPI(name, url, headers = {}, body = null, method = 'GET') {
  try {
    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timer);
    const data = await res.json().catch(() => null);
    if (res.ok) return { ok: true, data };
    return { ok: false, error: data?.error?.message || `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function testClaude() {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Claude AI', 'SKIP', 'No API key');
  const r = await testAPI('Claude', 'https://api.anthropic.com/v1/messages', {
    'x-api-key': key,
    'Content-Type': 'application/json',
    'anthropic-version': '2023-06-01'
  }, { model: 'claude-sonnet-4-20250514', max_tokens: 10, messages: [{ role: 'user', content: 'Hi' }] }, 'POST');
  log('Claude AI', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testOpenAI() {
  const key = process.env.OPENAI_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('OpenAI', 'SKIP', 'No API key');
  const r = await testAPI('OpenAI', 'https://api.openai.com/v1/models', {
    'Authorization': `Bearer ${key}`
  });
  log('OpenAI', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testPerplexity() {
  const key = process.env.PERPLEXITY_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Perplexity', 'SKIP', 'No API key');
  const r = await testAPI('Perplexity', 'https://api.perplexity.ai/chat/completions', {
    'Authorization': `Bearer ${key}`,
    'Content-Type': 'application/json'
  }, { model: 'sonar', messages: [{ role: 'user', content: 'Hi' }], max_tokens: 10 }, 'POST');
  log('Perplexity', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testGitHub() {
  const key = process.env.GITHUB_TOKEN;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('GitHub', 'SKIP', 'No API key');
  const r = await testAPI('GitHub', 'https://api.github.com/user', {
    'Authorization': `Bearer ${key}`,
    'User-Agent': 'Rudibot'
  });
  log('GitHub', r.ok ? 'OK' : 'FAIL', r.ok ? `User: ${r.data?.login}` : r.error);
}

async function testShopify() {
  const token = process.env.SHOPIFY_ADMIN_TOKEN;
  const store = process.env.SHOPIFY_STORE_URL;
  if (!token || !store || token.includes('DEIN') || token.includes('PLACEHOLDER')) {
    return log('Shopify', 'SKIP', 'Invalid or missing token');
  }
  const r = await testAPI('Shopify', `https://${store}/admin/api/2025-01/shop.json`, {
    'X-Shopify-Access-Token': token
  });
  log('Shopify', r.ok ? 'OK' : 'FAIL', r.ok ? `Store: ${r.data?.shop?.name}` : r.error);
}

async function testPrintify() {
  const key = process.env.PRINTIFY_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Printify', 'SKIP', 'No API key');
  const r = await testAPI('Printify', 'https://api.printify.com/v1/shops.json', {
    'Authorization': `Bearer ${key}`
  });
  log('Printify', r.ok ? 'OK' : 'FAIL', r.ok ? `Shops: ${r.data?.data?.length || 0}` : r.error);
}

async function testDigistore() {
  const key = process.env.DIGISTORE_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Digistore24', 'SKIP', 'No API key');
  // Digistore API needs specific endpoint, just validate key format
  log('Digistore24', 'INFO', `Key present: ${key.split('-')[0]}...`);
}

async function testSendGrid() {
  const key = process.env.SENDGRID_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('SendGrid', 'SKIP', 'No API key');
  const r = await testAPI('SendGrid', 'https://api.sendgrid.com/v3/user/profile', {
    'Authorization': `Bearer ${key}`
  });
  log('SendGrid', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testSupabase() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY;
  if (!url || !key) return log('Supabase', 'SKIP', 'Missing config');
  const r = await testAPI('Supabase', `${url}/rest/v1/`, {
    'apikey': key,
    'Authorization': `Bearer ${key}`
  });
  log('Supabase', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testTelegram() {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token || token.includes('DEIN') || token.includes('PLACEHOLDER')) return log('Telegram', 'SKIP', 'No token');
  const r = await testAPI('Telegram', `https://api.telegram.org/bot${token}/getMe`);
  log('Telegram', r.ok && r.data?.ok ? 'OK' : 'FAIL', r.ok && r.data?.ok ? `Bot: @${r.data.result.username}` : r.error || 'Invalid token');
}

async function testStripe() {
  const key = process.env.STRIPE_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Stripe', 'SKIP', 'No API key');
  const r = await testAPI('Stripe', 'https://api.stripe.com/v1/account', {
    'Authorization': `Bearer ${key}`
  });
  log('Stripe', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testYouTube() {
  const key = process.env.YOUTUBE_API_KEY;
  const channelId = process.env.YOUTUBE_CHANNEL_ID;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('YouTube', 'SKIP', 'No API key');
  const r = await testAPI('YouTube', `https://www.googleapis.com/youtube/v3/channels?part=snippet&id=${channelId}&key=${key}`);
  log('YouTube', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testGoogleAI() {
  const key = process.env.GOOGLE_AI_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Google AI', 'SKIP', 'No API key');
  const r = await testAPI('Google AI', `https://generativelanguage.googleapis.com/v1/models?key=${key}`);
  log('Google AI', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testKlaviyo() {
  const key = process.env.KLAVIYO_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Klaviyo', 'SKIP', 'No API key');
  const r = await testAPI('Klaviyo', 'https://a.klaviyo.com/api/profiles/', {
    'Authorization': `Klaviyo-API-Key ${key}`,
    'revision': '2023-02-22'
  });
  log('Klaviyo', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

async function testMailchimp() {
  const key = process.env.MAILCHIMP_API_KEY;
  if (!key || key.includes('DEIN') || key.includes('PLACEHOLDER')) return log('Mailchimp', 'SKIP', 'No API key');
  const dc = process.env.MAILCHIMP_SERVER_PREFIX || 'us18';
  const r = await testAPI('Mailchimp', `https://${dc}.api.mailchimp.com/3.0/ping`, {
    'Authorization': `Bearer ${key}`
  });
  log('Mailchimp', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// ── Main ────────────────────────────────────────────────────
console.log('\n═══════════════════════════════════════════════════════════');
console.log('  RUDIBOT API TEST REPORT');
console.log('═══════════════════════════════════════════════════════════\n');
console.log('API                  | Status | Details');
console.log('───────────────────────────────────────────────────────────');

(async () => {
  await testClaude();
  await testOpenAI();
  await testPerplexity();
  await testGitHub();
  await testShopify();
  await testPrintify();
  await testDigistore();
  await testSupabase();
  await testTelegram();
  await testStripe();
  await testSendGrid();
  await testYouTube();
  await testGoogleAI();
  await testKlaviyo();
  await testMailchimp();

  const ok = results.filter(r => r.status === 'OK').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  const skip = results.filter(r => r.status === 'SKIP' || r.status === 'INFO').length;

  console.log('\n───────────────────────────────────────────────────────────');
  console.log(`✅ Working: ${ok}  |  ❌ Failed: ${fail}  |  ⚠️  Skipped/Info: ${skip}`);
  console.log('═══════════════════════════════════════════════════════════\n');

  process.exit(0);
})();
