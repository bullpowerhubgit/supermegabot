#!/usr/bin/env node
require('dotenv').config();

// Einfacher Test ohne fetch - nur Key-Validierung
const tests = [
  { name: 'GitHub', key: 'GITHUB_TOKEN', pattern: /^ghp_[a-zA-Z0-9]{36}$/ },
  { name: 'Claude', key: 'ANTHROPIC_API_KEY', pattern: /^sk-ant-api03-[a-zA-Z0-9_-]{95,}$/ },
  { name: 'OpenAI', key: 'OPENAI_API_KEY', pattern: /^sk-proj-[a-zA-Z0-9_-]{48,}$/ },
  { name: 'Perplexity', key: 'PERPLEXITY_API_KEY', pattern: /^pplx-[a-zA-Z0-9_-]{24,}$/ },
  { name: 'Shopify', key: 'SHOPIFY_ADMIN_TOKEN', pattern: /^shpat_[a-zA-Z0-9]{32}$/ },
  { name: 'Printify', key: 'PRINTIFY_API_KEY', pattern: /^eyJ[a-zA-Z0-9._-]{500,}$/ },
  { name: 'Telegram', key: 'TELEGRAM_BOT_TOKEN', pattern: /^\d+:[a-zA-Z0-9_-]{34}$/ },
  { name: 'Stripe', key: 'STRIPE_API_KEY', pattern: /^sk_live_[a-zA-Z0-9]{24,}$/ },
  { name: 'Supabase', key: 'SUPABASE_ANON_KEY', pattern: /^eyJ[a-zA-Z0-9._-]{150,}$/ },
  { name: 'YouTube', key: 'YOUTUBE_API_KEY', pattern: /^AIzaSy[a-zA-Z0-9_-]{39}$/ },
  { name: 'Google AI', key: 'GOOGLE_AI_API_KEY', pattern: /^AIzaSy[a-zA-Z0-9_-]{39}$/ },
  { name: 'Mailchimp', key: 'MAILCHIMP_API_KEY', pattern: /^[a-f0-9]{32}-us\d{2}$/ },
  { name: 'Klaviyo', key: 'KLAVIYO_API_KEY', pattern: /^pk_[a-zA-Z0-9_-]{32,}$/ },
];

console.log('═══════════════════════════════════════════');
console.log('  RUDIBOT API KEY VALIDATION');
console.log('═══════════════════════════════════════════\n');

let valid = 0, invalid = 0, missing = 0;

for (const test of tests) {
  const value = process.env[test.key];
  if (!value) {
    console.log(`❌ ${test.name.padEnd(12)} | MISSING      | Key nicht gesetzt`);
    missing++;
  } else if (test.pattern.test(value)) {
    console.log(`✅ ${test.name.padEnd(12)} | VALID        | Format korrekt`);
    valid++;
  } else {
    console.log(`❌ ${test.name.padEnd(12)} | INVALID      | Format falsch: ${value.slice(0,20)}...`);
    invalid++;
  }
}

console.log('\n═══════════════════════════════════════════');
console.log(`✅ Valid: ${valid}  |  ❌ Invalid: ${invalid}  |  ❌ Missing: ${missing}`);
console.log('\nEmpfehlung:');
if (invalid > 0) console.log('- Keys mit ungültigem Format erneuern');
if (missing > 0) console.log('- Fehlende Keys in .env eintragen');
if (valid === tests.length) console.log('- Alle Keys haben korrektes Format!');

// Spezielle Checks
console.log('\n═══════════════════════════════════════════');
console.log('  SPEZIELLE PRÜFUNGEN');
console.log('═══════════════════════════════════════════');

// Shopify Store URL
if (process.env.SHOPIFY_STORE_URL) {
  const url = process.env.SHOPIFY_STORE_URL;
  const valid = /^[a-zA-Z0-9-]+\.myshopify\.com$/.test(url);
  console.log(`${valid ? '✅' : '❌'} Shopify URL   | ${valid ? 'VALID' : 'INVALID'} | ${url}`);
}

// Telegram Admin ID Check
if (process.env.TELEGRAM_ADMIN_ID) {
  const id = process.env.TELEGRAM_ADMIN_ID;
  const isNumeric = /^\d+$/.test(id);
  console.log(`${isNumeric ? '✅' : '❌'} Telegram ID  | ${isNumeric ? 'VALID' : 'INVALID'} | ${id}`);
}

console.log('\n═══════════════════════════════════════════\n');
