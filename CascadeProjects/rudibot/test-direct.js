#!/usr/bin/env node
// Direct API key testing without server
require('dotenv').config();

const colors = {
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m'
};

function log(status, service, message) {
  const color = status === 'OK' ? colors.green : status === 'FAIL' ? colors.red : colors.yellow;
  console.log(`${color}${status}${colors.reset} ${service} - ${message}`);
}

async function testDirectAPIs() {
  console.log(`\n${colors.blue}=== Direct API Key Testing ===${colors.reset}\n`);
  
  // Test each API directly
  const tests = [];
  
  // Anthropic
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'x-api-key': process.env.ANTHROPIC_API_KEY, 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({ model: 'claude-sonnet-4-20250514', max_tokens: 10, messages: [{role: 'user', content: 'Hi'}] })
    });
    const data = await res.json();
    log(res.ok ? 'OK' : 'FAIL', 'Anthropic', res.ok ? 'Working' : data.error?.message || 'Invalid key');
  } catch(e) { log('FAIL', 'Anthropic', e.message); }

  // OpenAI
  try {
    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'gpt-4o-mini', max_tokens: 5, messages: [{role: 'user', content: 'Hi'}] })
    });
    const data = await res.json();
    log(res.ok ? 'OK' : 'FAIL', 'OpenAI', res.ok ? 'Working' : data.error?.message || 'Invalid key');
  } catch(e) { log('FAIL', 'OpenAI', e.message); }

  // Perplexity
  try {
    const res = await fetch('https://api.perplexity.ai/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'sonar-pro', messages: [{role: 'user', content: 'Hi'}] })
    });
    const data = await res.json();
    log(res.ok ? 'OK' : 'FAIL', 'Perplexity', res.ok ? 'Working' : data.error?.message || 'Invalid key');
  } catch(e) { log('FAIL', 'Perplexity', e.message); }

  // GitHub
  try {
    const res = await fetch('https://api.github.com/user', {
      headers: { 'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`, 'User-Agent': 'AutoPilot-Bot' }
    });
    const data = await res.json();
    log(res.ok ? 'OK' : 'FAIL', 'GitHub', res.ok ? `User: ${data.login}` : data.message || 'Invalid token');
  } catch(e) { log('FAIL', 'GitHub', e.message); }

  // Telegram
  try {
    const res = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/getMe`);
    const data = await res.json();
    log(res.ok && data.ok ? 'OK' : 'FAIL', 'Telegram', data.ok ? `Bot: ${data.result.first_name}` : data.description || 'Invalid token');
  } catch(e) { log('FAIL', 'Telegram', e.message); }

  // Shopify
  if (process.env.SHOPIFY_ADMIN_TOKEN && !process.env.SHOPIFY_ADMIN_TOKEN.includes('PLACEHOLDER')) {
    try {
      const res = await fetch(`https://${process.env.SHOPIFY_STORE_URL}/admin/api/${process.env.SHOPIFY_API_VERSION || '2025-01'}/shop.json`, {
        headers: { 'X-Shopify-Access-Token': process.env.SHOPIFY_ADMIN_TOKEN }
      });
      const data = await res.json();
      log(res.ok ? 'OK' : 'FAIL', 'Shopify', res.ok ? `Store: ${data.shop?.name}` : data.errors || 'Invalid token');
    } catch(e) { log('FAIL', 'Shopify', e.message); }
  } else {
    log('FAIL', 'Shopify', 'Token is PLACEHOLDER');
  }

  // Supabase
  try {
    const res = await fetch(`${process.env.SUPABASE_URL}/rest/v1/`, {
      headers: { 'apikey': process.env.SUPABASE_ANON_KEY, 'Authorization': `Bearer ${process.env.SUPABASE_ANON_KEY}` }
    });
    log(res.ok || res.status === 400 ? 'OK' : 'FAIL', 'Supabase', res.ok ? 'Accessible' : 'Check keys');
  } catch(e) { log('FAIL', 'Supabase', e.message); }

  // Stripe
  try {
    const res = await fetch('https://api.stripe.com/v1/account', {
      headers: { 'Authorization': `Bearer ${process.env.STRIPE_API_KEY}` }
    });
    const data = await res.json();
    log(res.ok ? 'OK' : 'FAIL', 'Stripe', res.ok ? 'Working' : data.error?.message || 'Invalid key');
  } catch(e) { log('FAIL', 'Stripe', e.message); }

  // Printify
  try {
    const res = await fetch('https://api.printify.com/v1/shops.json', {
      headers: { 'Authorization': `Bearer ${process.env.PRINTIFY_API_KEY}` }
    });
    const data = await res.json();
    log(res.ok ? 'OK' : 'FAIL', 'Printify', res.ok ? `Shops: ${data.data?.length || 0}` : data.message || 'Invalid key');
  } catch(e) { log('FAIL', 'Printify', e.message); }

  console.log(`\n${colors.blue}=== Testing Complete ===${colors.reset}\n`);
}

testDirectAPIs().catch(console.error);
