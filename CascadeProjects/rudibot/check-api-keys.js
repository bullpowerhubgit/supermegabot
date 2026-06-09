#!/usr/bin/env node
/**
 * Simple API Key Check - reads .env and .env.new for comparison
 */
const fs = require('fs');
const path = require('path');

function parseEnv(content) {
  const vars = {};
  for (const line of content.split('\n')) {
    const m = line.match(/^([A-Za-z0-9_]+)=(.*)$/);
    if (m) vars[m[1]] = m[2];
  }
  return vars;
}

function extractKeysFromNew(content) {
  const keys = {};
  // GitHub tokens
  const githubTokens = content.match(/gh[pst]_[A-Za-z0-9]{20,}/g);
  if (githubTokens) keys.github = githubTokens;
  
  // Anthropic key
  const anthropic = content.match(/sk-ant-api03-[A-Za-z0-9_-]+/);
  if (anthropic) keys.anthropic = anthropic[0];
  
  // OpenAI key
  const openai = content.match(/sk-proj-[A-Za-z0-9_-]+/);
  if (openai) keys.openai = openai[0];
  
  // Supabase keys
  const supabaseUrl = content.match(/(https:\/\/[a-z0-9]+\.supabase\.co)/);
  if (supabaseUrl) keys.supabase_url = supabaseUrl[1];
  const supabaseAnon = content.match(/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[^\s]+/g);
  if (supabaseAnon) keys.supabase_keys = supabaseAnon;
  
  // Stripe keys
  const stripePub = content.match(/pk_live_[A-Za-z0-9]{20,}/);
  if (stripePub) keys.stripe_pub = stripePub[0];
  const stripeSec = content.match(/sk_live_[A-Za-z0-9]{20,}/);
  if (stripeSec) keys.stripe_sec = stripeSec[0];
  
  // Telegram
  const telegram = content.match(/(\d+:[A-Za-z0-9_-]{20,})/);
  if (telegram) keys.telegram = telegram[1];
  
  // Vercel team
  const vercel = content.match(/(team_[A-Za-z0-9]{20,})/);
  if (vercel) keys.vercel = vercel[1];
  
  return keys;
}

function checkKey(name, value, source = '.env') {
  if (!value) return { status: 'MISSING', icon: '❌', msg: 'Not set' };
  if (value.includes('PLACEHOLDER') || value.includes('DEIN') || value.includes('HIER')) {
    return { status: 'PLACEHOLDER', icon: '⚠️', msg: 'Placeholder value' };
  }
  if (value.length < 10) return { status: 'SHORT', icon: '⚠️', msg: 'Suspiciously short' };
  return { status: 'PRESENT', icon: '✅', msg: `Present (${value.length} chars)` };
}

console.log('\n═══════════════════════════════════════════════════════════');
console.log('  RUDIBOT API KEY STATUS');
console.log('═══════════════════════════════════════════════════════════\n');

// Read .env
const envPath = path.join(__dirname, '.env');
const envContent = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';
const envVars = parseEnv(envContent);

// Read .env.new
const envNewPath = path.join(__dirname, '.env.new');
const envNewContent = fs.existsSync(envNewPath) ? fs.readFileSync(envNewPath, 'utf8') : '';
const newKeys = extractKeysFromNew(envNewContent);

const checks = [
  ['Claude AI', 'ANTHROPIC_API_KEY'],
  ['OpenAI', 'OPENAI_API_KEY'],
  ['Perplexity', 'PERPLEXITY_API_KEY'],
  ['GitHub', 'GITHUB_TOKEN'],
  ['Shopify Store 1', 'SHOPIFY_ADMIN_TOKEN'],
  ['Shopify Store 2', 'SHOPIFY_STORE2_TOKEN'],
  ['Printify', 'PRINTIFY_API_KEY'],
  ['SendGrid', 'SENDGRID_API_KEY'],
  ['Supabase URL', 'SUPABASE_URL'],
  ['Supabase Anon', 'SUPABASE_ANON_KEY'],
  ['Supabase Secret', 'SUPABASE_SERVICE_ROLE_KEY'],
  ['Telegram', 'TELEGRAM_BOT_TOKEN'],
  ['Stripe', 'STRIPE_API_KEY'],
  ['YouTube', 'YOUTUBE_API_KEY'],
  ['Google AI', 'GOOGLE_AI_API_KEY'],
  ['Klaviyo', 'KLAVIYO_API_KEY'],
  ['Mailchimp', 'MAILCHIMP_API_KEY'],
  ['Vercel Token', 'VERCEL_TOKEN'],
];

console.log('API                  | Status      | Details');
console.log('───────────────────────────────────────────────────────────');

for (const [name, varName] of checks) {
  const result = checkKey(name, envVars[varName]);
  console.log(`${result.icon} ${name.padEnd(20)} | ${result.status.padEnd(11)} | ${result.msg}`);
}

console.log('\n───────────────────────────────────────────────────────────');
console.log('Keys extracted from .env.new:');
for (const [k, v] of Object.entries(newKeys)) {
  const display = Array.isArray(v) ? `${v.length} keys found` : (typeof v === 'string' ? `${v.substring(0, 20)}...` : v);
  console.log(`  ${k}: ${display}`);
}

console.log('\n═══════════════════════════════════════════════════════════\n');
