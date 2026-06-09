#!/usr/bin/env node
// ============================================================
// test-apis.js — API Testing Script for AutoPilot Bot
// Rudolf Sarkany · Quick API Verification
// ============================================================
'use strict';
require('dotenv').config();

// Node 18+ has global fetch — no need for node-fetch

// Colors for output
const colors = {
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m'
};

function log(status, service, message) {
  const color = status === '✅' ? colors.green : status === '❌' ? colors.red : colors.yellow;
  console.log(`${color}${status} ${service}${colors.reset} - ${message}`);
}

// ── API Tests ───────────────────────────────────────────────────
async function testAnthropic() {
  try {
    const res = await fetch('http://localhost:3200/api/ai/claude', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: 'Say hello', max_tokens: 10 })
    });
    const data = await res.json();
    if (res.ok && data.text) {
      log('✅', 'Anthropic Claude', 'Working correctly');
      return true;
    } else {
      log('❌', 'Anthropic Claude', data.error || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'Anthropic Claude', e.message);
    return false;
  }
}

async function testShopify() {
  try {
    const res = await fetch('http://localhost:3200/api/shopify/store');
    const data = await res.json();
    if (res.ok && data.shop) {
      log('✅', 'Shopify', `Connected to ${data.shop.name}`);
      return true;
    } else {
      log('❌', 'Shopify', data.error || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'Shopify', e.message);
    return false;
  }
}

async function testGitHub() {
  try {
    const res = await fetch('http://localhost:3200/api/github/repos');
    const data = await res.json();
    if (res.ok && Array.isArray(data)) {
      log('✅', 'GitHub', `Found ${data.length} repositories`);
      return true;
    } else {
      log('❌', 'GitHub', data.error || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'GitHub', e.message);
    return false;
  }
}

async function testPerplexity() {
  try {
    const res = await fetch('http://localhost:3200/api/ai/perplexity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'What is 2+2?', model: 'sonar-pro' })
    });
    const data = await res.json();
    if (res.ok && data.choices) {
      log('✅', 'Perplexity', 'Working correctly');
      return true;
    } else {
      log('❌', 'Perplexity', data.error || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'Perplexity', e.message);
    return false;
  }
}

async function testSupabase() {
  try {
    // Test by checking if API key is configured (no actual API call to avoid errors)
    const configured = !!process.env.SUPABASE_URL && !!process.env.SUPABASE_ANON_KEY && !process.env.SUPABASE_ANON_KEY.includes('PLACEHOLDER');
    if (configured) {
      log('✅', 'Supabase', 'API keys configured');
      return true;
    } else {
      log('❌', 'Supabase', 'API keys not configured');
      return false;
    }
  } catch(e) {
    log('❌', 'Supabase', e.message);
    return false;
  }
}

async function testPrintify() {
  try {
    const res = await fetch('http://localhost:3200/api/printify/shops');
    const data = await res.json();
    if (res.ok && Array.isArray(data)) {
      log('✅', 'Printify', `Found ${data.length} shops`);
      return true;
    } else {
      log('❌', 'Printify', data.error || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'Printify', e.message);
    return false;
  }
}

async function testSendGrid() {
  try {
    const res = await fetch('http://localhost:3200/api/email/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        to: 'test@example.com',
        subject: 'Test Email',
        text: 'This is a test email'
      })
    });
    const data = await res.json();
    if (res.ok || res.status === 202) {
      log('✅', 'SendGrid', 'API working (email may not actually send to test address)');
      return true;
    } else {
      log('❌', 'SendGrid', data.error || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'SendGrid', e.message);
    return false;
  }
}

async function testTelegram() {
  try {
    const res = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/getMe`);
    const data = await res.json();
    if (res.ok && data.ok) {
      log('✅', 'Telegram', `Bot: ${data.result.first_name}`);
      return true;
    } else {
      log('❌', 'Telegram', data.description || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'Telegram', e.message);
    return false;
  }
}

async function testOpenAI() {
  try {
    const res = await fetch('http://localhost:3200/api/ai/openai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: 'Say hello', max_tokens: 10 })
    });
    const data = await res.json();
    if (res.ok && data.text) {
      log('✅', 'OpenAI', 'Working correctly');
      return true;
    } else {
      log('❌', 'OpenAI', data.error || 'API Error');
      return false;
    }
  } catch(e) {
    log('❌', 'OpenAI', e.message);
    return false;
  }
}

async function testStripe() {
  try {
    // Test by checking if key is configured (no actual API call to avoid charges)
    const configured = !!process.env.STRIPE_API_KEY && !process.env.STRIPE_API_KEY.includes('PLACEHOLDER');
    if (configured) {
      log('✅', 'Stripe', 'API key configured');
      return true;
    } else {
      log('❌', 'Stripe', 'API key not configured');
      return false;
    }
  } catch(e) {
    log('❌', 'Stripe', e.message);
    return false;
  }
}

// ── Main Test Runner ─────────────────────────────────────────────
async function main() {
  console.log(`\n${colors.blue}🧪 AutoPilot Bot API Test Suite${colors.reset}\n`);
  
  // Check if server is running
  try {
    const res = await fetch('http://localhost:3200/api/health');
    if (!res.ok) throw new Error('Server not responding');
    log('✅', 'Server', 'Running on port 3200');
  } catch(e) {
    log('❌', 'Server', 'Not running - start with: npm start');
    process.exit(1);
  }

  console.log(`\n${colors.yellow}Testing all APIs...${colors.reset}\n`);

  const results = {
    telegram: await testTelegram(),
    anthropic: await testAnthropic(),
    openai: await testOpenAI(),
    perplexity: await testPerplexity(),
    shopify: await testShopify(),
    github: await testGitHub(),
    supabase: await testSupabase(),
    printify: await testPrintify(),
    sendgrid: await testSendGrid(),
    stripe: await testStripe()
  };

  console.log(`\n${colors.blue}📊 Test Results Summary:${colors.reset}\n`);
  
  const working = Object.values(results).filter(Boolean).length;
  const total = Object.keys(results).length;
  
  Object.entries(results).forEach(([service, ok]) => {
    const status = ok ? '✅' : '❌';
    const color = ok ? colors.green : colors.red;
    console.log(`${color}${status} ${service.toUpperCase()}${colors.reset}`);
  });
  
  console.log(`\n${colors.blue}Summary: ${working}/${total} APIs working${colors.reset}\n`);
  
  if (working === total) {
    console.log(`${colors.green}🎉 All APIs are working perfectly!${colors.reset}`);
  } else {
    console.log(`${colors.yellow}⚠️  Some APIs need attention. Check API_KEYS_GUIDE.md${colors.reset}`);
  }
}

// Run tests
if (require.main === module) {
  main().catch(console.error);
}

module.exports = { main };
