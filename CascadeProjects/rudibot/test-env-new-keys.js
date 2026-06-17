const fs = require('fs');
const path = require('path');

// Load environment variables from .env.new
require('dotenv').config({ path: path.join(__dirname, '.env.new') });

// Helper function to test API
async function testAPI(name, url, headers = {}, body = null, method = 'GET') {
  try {
    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);
    
    const res = await fetch(url, { ...options, signal: AbortSignal.timeout(10000) });
    const data = await res.json().catch(() => null);
    
    if (res.ok) return { ok: true, data };
    return { ok: false, error: data?.error?.message || `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

// Extract API keys from .env.new content
function extractAPIKeys() {
  const envNewContent = fs.readFileSync(path.join(__dirname, '.env.new'), 'utf8');
  const keys = {};
  
  // GitHub tokens
  const githubTokens = envNewContent.match(/ghp_[A-Za-z0-9]{36}/g) || [];
  const githubPATs = envNewContent.match(/github_pat_[A-Za-z0-9_]{100,}/g) || [];
  
  if (githubTokens.length > 0) keys.GITHUB_TOKEN = githubTokens[0];
  if (githubPATs.length > 0) keys.GITHUB_FINE_GRAINED_PAT = githubPATs[0];
  if (githubPATs.length > 1) keys.GITHUB_FINE_GRAINED_PAT_2 = githubPATs[1];
  
  // Anthropic Claude
  const claudeKeys = envNewContent.match(/sk-ant-api03-[A-Za-z0-9_-]{95,}/g) || [];
  if (claudeKeys.length > 0) keys.ANTHROPIC_API_KEY = claudeKeys[0];
  
  // OpenAI
  const openaiKeys = envNewContent.match(/sk-proj-[A-Za-z0-9_-]{48,}/g) || [];
  if (openaiKeys.length > 0) keys.OPENAI_API_KEY = openaiKeys[0];
  
  // Supabase
  const supabaseUrls = envNewContent.match(/https:\/\/[a-z0-9-]+\.supabase\.co/g) || [];
  const supabaseAnonKeys = envNewContent.match(/eyJ[a-zA-Z0-9._-]{300,}/g) || [];
  
  if (supabaseUrls.length > 0) keys.SUPABASE_URL = supabaseUrls[0];
  if (supabaseAnonKeys.length > 0) keys.SUPABASE_ANON_KEY = supabaseAnonKeys[0];
  if (supabaseAnonKeys.length > 1) keys.SUPABASE_SERVICE_KEY = supabaseAnonKeys[1];
  
  // Stripe
  const stripeKeys = envNewContent.match(/sk_live_[A-Za-z0-9]{24,}/g) || [];
  const stripePublishable = envNewContent.match(/pk_live_[A-Za-z0-9]{24,}/g) || [];
  
  if (stripeKeys.length > 0) keys.STRIPE_API_KEY = stripeKeys[0];
  if (stripePublishable.length > 0) keys.STRIPE_PUBLISHABLE_KEY = stripePublishable[0];
  
  // Telegram
  const telegramTokens = envNewContent.match(/[0-9]+:[A-Za-z0-9_-]{35}/g) || [];
  if (telegramTokens.length > 0) keys.TELEGRAM_BOT_TOKEN = telegramTokens[0];
  
  // Shopify Print API
  const printTokens = envNewContent.match(/prtapi_[A-Za-z0-9]{32}/g) || [];
  if (printTokens.length > 0) keys.SHOPIFY_PRINT_API_TOKEN = printTokens[0];
  
  // Vercel
  const vercelTeamIds = envNewContent.match(/team_[A-Za-z0-9_-]{20,}/g) || [];
  if (vercelTeamIds.length > 0) keys.VERCEL_TEAM_ID = vercelTeamIds[0];
  
  return keys;
}

// Test functions for each API
async function testGitHub() {
  const key = process.env.GITHUB_TOKEN || extractAPIKeys().GITHUB_TOKEN;
  if (!key) return { ok: false, error: 'No GitHub token found' };
  
  const r = await testAPI('GitHub', 'https://api.github.com/user', {
    'Authorization': `token ${key}`,
    'User-Agent': 'RudiBot'
  });
  log('GitHub API', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  return r;
}

async function testClaude() {
  const key = process.env.ANTHROPIC_API_KEY || extractAPIKeys().ANTHROPIC_API_KEY;
  if (!key) return { ok: false, error: 'No Claude key found' };
  
  const r = await testAPI('Claude', 'https://api.anthropic.com/v1/messages', {
    'x-api-key': key,
    'Content-Type': 'application/json',
    'anthropic-version': '2023-06-01'
  }, {
    model: 'claude-3-5-sonnet-20241022',
    max_tokens: 10,
    messages: [{ role: 'user', content: 'Hi' }]
  }, 'POST');
  log('Claude AI', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  return r;
}

async function testOpenAI() {
  const key = process.env.OPENAI_API_KEY || extractAPIKeys().OPENAI_API_KEY;
  if (!key) return { ok: false, error: 'No OpenAI key found' };
  
  const r = await testAPI('OpenAI', 'https://api.openai.com/v1/chat/completions', {
    'Authorization': `Bearer ${key}`,
    'Content-Type': 'application/json'
  }, {
    model: 'gpt-3.5-turbo',
    messages: [{ role: 'user', content: 'Hi' }],
    max_tokens: 10
  }, 'POST');
  log('OpenAI GPT', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  return r;
}

async function testSupabase() {
  const url = process.env.SUPABASE_URL || extractAPIKeys().SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY || extractAPIKeys().SUPABASE_ANON_KEY;
  if (!url || !key) return { ok: false, error: 'No Supabase credentials found' };
  
  const r = await testAPI('Supabase', `${url}/rest/v1/`, {
    'apikey': key,
    'Authorization': `Bearer ${key}`
  });
  log('Supabase', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  return r;
}

async function testStripe() {
  const key = process.env.STRIPE_API_KEY || extractAPIKeys().STRIPE_API_KEY;
  if (!key) return { ok: false, error: 'No Stripe key found' };
  
  const r = await testAPI('Stripe', 'https://api.stripe.com/v1/account', {
    'Authorization': `Bearer ${key}`
  });
  log('Stripe API', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  return r;
}

async function testTelegram() {
  const token = process.env.TELEGRAM_BOT_TOKEN || extractAPIKeys().TELEGRAM_BOT_TOKEN;
  if (!token) return { ok: false, error: 'No Telegram token found' };
  
  const r = await testAPI('Telegram', `https://api.telegram.org/bot${token}/getMe`);
  log('Telegram Bot', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  return r;
}

async function testShopifyPrint() {
  const token = process.env.SHOPIFY_PRINT_API_TOKEN || extractAPIKeys().SHOPIFY_PRINT_API_TOKEN;
  if (!token) return { ok: false, error: 'No Shopify Print token found' };
  
  const r = await testAPI('Shopify Print', 'https://api.printify.com/v1/shops.json', {
    'Authorization': `Bearer ${token}`
  });
  log('Shopify Print API', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  return r;
}

// Logging function
function log(service, status, message) {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${service}: ${status} - ${message}`);
}

// Main test function
async function testAllAPIs() {
  console.log('='.repeat(60));
  console.log('TESTING API KEYS FROM .env.new');
  console.log('='.repeat(60));
  
  const extractedKeys = extractAPIKeys();
  console.log('\nExtracted API Keys:');
  Object.entries(extractedKeys).forEach(([key, value]) => {
    console.log(`  ${key}: ${value ? value.substring(0, 20) + '...' : 'Not found'}`);
  });
  console.log('\nTesting APIs:\n');
  
  const results = {};
  
  // Test each API
  results.github = await testGitHub();
  results.claude = await testClaude();
  results.openai = await testOpenAI();
  results.supabase = await testSupabase();
  results.stripe = await testStripe();
  results.telegram = await testTelegram();
  results.shopifyPrint = await testShopifyPrint();
  
  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('SUMMARY');
  console.log('='.repeat(60));
  
  const working = Object.values(results).filter(r => r.ok).length;
  const total = Object.keys(results).length;
  
  console.log(`\nWorking APIs: ${working}/${total} (${Math.round(working/total*100)}%)`);
  console.log('\nDetailed Results:');
  
  Object.entries(results).forEach(([api, result]) => {
    const status = result.ok ? '✅ OK' : '❌ FAIL';
    console.log(`  ${api}: ${status}`);
  });
  
  return results;
}

// Run tests
if (require.main === module) {
  testAllAPIs().catch(console.error);
}

module.exports = { testAllAPIs, extractAPIKeys };
