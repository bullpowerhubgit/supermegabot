#!/usr/bin/env node
/**
 * Live-Connection Check for RUDIBOT
 * Phase 1: Shopify Re-activation & API health
 *
 * Usage:
 *   node scripts/test-live-connections.js
 *   node scripts/test-live-connections.js --verbose
 *   node scripts/test-live-connections.js --write-env
 */
'use strict';
require('dotenv').config();

const fs = require('fs');
const path = require('path');

// ── Config ───────────────────────────────────────────────────
const CHECKS = {
  shopify: {
    name: 'Shopify Store',
    required: true,
    url: () => `https://${process.env.SHOPIFY_STORE_URL}/admin/api/${process.env.SHOPIFY_API_VERSION || '2025-01'}/shop.json`,
    headers: () => ({ 'X-Shopify-Access-Token': process.env.SHOPIFY_ADMIN_TOKEN }),
    validate: async (json) => {
      if (!json.shop) throw new Error('Missing shop object');
      return {
        store: json.shop.name,
        domain: json.shop.domain,
        plan: json.shop.plan_name,
        currency: json.shop.currency,
        timezone: json.shop.iana_timezone,
        products_count: json.shop.products_count,
        orders_count: json.shop.orders_count,
      };
    }
  },
  shopifyOrders: {
    name: 'Shopify Orders (Live)',
    required: true,
    url: () => `https://${process.env.SHOPIFY_STORE_URL}/admin/api/${process.env.SHOPIFY_API_VERSION || '2025-01'}/orders.json?status=any&limit=5`,
    headers: () => ({ 'X-Shopify-Access-Token': process.env.SHOPIFY_ADMIN_TOKEN }),
    validate: async (json) => {
      if (!Array.isArray(json.orders)) throw new Error('Missing orders array');
      const latest = json.orders[0];
      return {
        total_orders: json.orders.length,
        latest_order_id: latest?.id || null,
        latest_order_number: latest?.name || null,
        latest_order_total: latest?.total_price || null,
        latest_order_date: latest?.created_at || null,
        financial_status: latest?.financial_status || null,
      };
    }
  },
  shopifyProducts: {
    name: 'Shopify Products',
    required: false,
    url: () => `https://${process.env.SHOPIFY_STORE_URL}/admin/api/${process.env.SHOPIFY_API_VERSION || '2025-01'}/products.json?limit=5`,
    headers: () => ({ 'X-Shopify-Access-Token': process.env.SHOPIFY_ADMIN_TOKEN }),
    validate: async (json) => ({
      total_products: json.products?.length || 0,
      first_product: json.products?.[0]?.title || null,
    })
  },
  printify: {
    name: 'Printify',
    required: false,
    url: () => 'https://api.printify.com/v1/shops.json',
    headers: () => ({ 'Authorization': `Bearer ${process.env.PRINTIFY_API_KEY}` }),
    validate: async (json) => ({
      shops: json.data?.map(s => ({ id: s.id, title: s.title })) || [],
    })
  },
  paypal: {
    name: 'PayPal (OAuth)',
    required: false,
    url: () => {
      const base = process.env.PAYPAL_SANDBOX === 'true'
        ? 'https://api-m.sandbox.paypal.com'
        : 'https://api-m.paypal.com';
      return `${base}/v1/oauth2/token`;
    },
    headers: () => {
      const auth = Buffer.from(`${process.env.PAYPAL_CLIENT_ID}:${process.env.PAYPAL_CLIENT_SECRET}`).toString('base64');
      return {
        'Authorization': `Basic ${auth}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      };
    },
    method: 'POST',
    body: 'grant_type=client_credentials',
    validate: async (json) => {
      if (!json.access_token) throw new Error('No access_token');
      return { token_type: json.token_type, expires_in: json.expires_in };
    }
  },
  klaviyo: {
    name: 'Klaviyo',
    required: false,
    url: () => 'https://a.klaviyo.com/api/profiles/',
    headers: () => ({
      'Authorization': `Klaviyo-API-Key ${process.env.KLAVIYO_API_KEY}`,
      'revision': '2023-02-22',
    }),
    validate: async (json) => ({ profiles_count: json.data?.length || 0 })
  },
  telegram: {
    name: 'Telegram Bot',
    required: false,
    url: () => `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/getMe`,
    headers: () => ({}),
    validate: async (json) => {
      if (!json.ok) throw new Error(json.description || 'Telegram API error');
      return { bot_username: json.result.username, bot_id: json.result.id };
    }
  },
  bankImportPath: {
    name: 'Bank CSV Import Path',
    required: false,
    skipHttp: true,
    validate: async () => {
      const p = process.env.BANK_IMPORT_PATH || './imports/bank';
      const exists = fs.existsSync(p);
      const files = exists ? fs.readdirSync(p).filter(f => f.endsWith('.csv')) : [];
      return { path: p, exists, csv_files: files.length, csv_names: files.slice(0, 5) };
    }
  },
  envFile: {
    name: '.env File Health',
    required: true,
    skipHttp: true,
    validate: async () => {
      const envPath = path.join(__dirname, '..', '.env');
      const exists = fs.existsSync(envPath);
      const content = exists ? fs.readFileSync(envPath, 'utf-8') : '';
      const secrets = [];
      const lines = content.split('\n');
      const criticalKeys = [
        'SHOPIFY_STORE_URL', 'SHOPIFY_ADMIN_TOKEN',
        'PAYPAL_CLIENT_ID', 'PAYPAL_CLIENT_SECRET',
        'PRINTIFY_API_KEY', 'PRINTIFY_SHOP_ID',
        'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
        'ANTHROPIC_API_KEY', 'OPENAI_API_KEY',
      ];
      const foundKeys = [];
      for (const line of lines) {
        const match = line.match(/^([A-Z_]+)\s*=\s*(.+)$/);
        if (match) {
          const [, key, val] = match;
          if (criticalKeys.includes(key)) foundKeys.push(key);
          if (val.length > 4 && !val.includes('PLACEHOLDER') && !val.includes('your_')) {
            // looks like a real secret
          } else if (val.includes('PLACEHOLDER') || val.includes('your_')) {
            secrets.push(`${key} = PLACEHOLDER`);
          }
        }
      }
      const missingKeys = criticalKeys.filter(k => !foundKeys.includes(k));
      return {
        env_exists: exists,
        critical_keys_found: foundKeys.length,
        critical_keys_total: criticalKeys.length,
        missing_keys: missingKeys,
        placeholder_count: secrets.length,
        placeholders: secrets.slice(0, 5),
      };
    }
  }
};

// ── Colors ────────────────────────────────────────────────────
const C = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  dim: '\x1b[2m',
  bold: '\x1b[1m',
};

function ok(msg) { return `${C.green}✅${C.reset} ${msg}`; }
function fail(msg) { return `${C.red}❌${C.reset} ${msg}`; }
function warn(msg) { return `${C.yellow}⚠️${C.reset}  ${msg}`; }
function info(msg) { return `${C.cyan}ℹ️${C.reset}  ${msg}`; }

// ── Runner ────────────────────────────────────────────────────
async function runCheck(key, config, verbose) {
  const start = Date.now();
  const result = {
    key,
    name: config.name,
    required: config.required,
    status: 'pending',
    latency_ms: 0,
    data: null,
    error: null,
  };

  try {
    let json;
    if (config.skipHttp) {
      json = await config.validate();
      result.data = json;
    } else {
      const url = config.url();
      const method = config.method || 'GET';
      const headers = config.headers();
      const body = config.body || undefined;

      const res = await fetch(url, { method, headers, body, signal: AbortSignal.timeout(15000) });
      result.latency_ms = Date.now() - start;

      const text = await res.text();
      try { json = JSON.parse(text); } catch { json = { _raw: text.slice(0, 200) }; }

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${json?.error || text.slice(0, 200)}`);
      }

      result.data = await config.validate(json);
    }
    result.status = 'ok';
  } catch (err) {
    result.status = 'error';
    result.error = err.message;
    result.latency_ms = Date.now() - start;
  }

  return result;
}

async function main() {
  const args = process.argv.slice(2);
  const verbose = args.includes('--verbose') || args.includes('-v');
  const writeEnv = args.includes('--write-env');

  console.log(`\n${C.bold}RUDIBOT Live Connection Check${C.reset}`);
  console.log(`${C.dim}Phase 1: Shopify Reactivation & API Health${C.reset}\n`);

  const results = [];
  for (const [key, config] of Object.entries(CHECKS)) {
    const r = await runCheck(key, config, verbose);
    results.push(r);
  }

  // ── Print Results ───────────────────────────────────────────
  let passed = 0;
  let failed = 0;
  let criticalFailed = 0;

  for (const r of results) {
    const icon = r.status === 'ok' ? ok('') : r.required ? fail('') : warn('');
    const label = r.required ? `${r.name} ${C.dim}(required)${C.reset}` : r.name;
    console.log(`${icon} ${label}`);

    if (r.status === 'ok') {
      passed++;
      if (verbose && r.data) {
        for (const [k, v] of Object.entries(r.data)) {
          if (Array.isArray(v)) {
            console.log(`   ${C.dim}${k}:${C.reset} [${v.length} items]`);
            for (const item of v.slice(0, 3)) {
              console.log(`      ${C.dim}- ${JSON.stringify(item).slice(0, 80)}${C.reset}`);
            }
          } else {
            console.log(`   ${C.dim}${k}:${C.reset} ${v}`);
          }
        }
      }
      if (r.latency_ms > 0) {
        console.log(`   ${C.dim}latency: ${r.latency_ms}ms${C.reset}`);
      }
    } else {
      failed++;
      if (r.required) criticalFailed++;
      console.log(`   ${C.red}Error:${C.reset} ${r.error}`);
    }
    console.log('');
  }

  // ── Summary ─────────────────────────────────────────────────
  console.log(`${C.bold}Summary${C.reset}`);
  console.log(`  ${ok(`Passed: ${passed}/${results.length}`)}`);
  if (failed > 0) {
    console.log(`  ${fail(`Failed: ${failed}/${results.length}`)}`);
  }
  if (criticalFailed > 0) {
    console.log(`  ${fail(`Critical failures: ${criticalFailed}`)}`);
  }

  // ── Phase 1 Gate ────────────────────────────────────────────
  const shopifyOk = results.find(r => r.key === 'shopify')?.status === 'ok';
  const ordersOk = results.find(r => r.key === 'shopifyOrders')?.status === 'ok';
  const envOk = results.find(r => r.key === 'envFile')?.status === 'ok';

  console.log(`\n${C.bold}Phase 1 Gate${C.reset}`);
  if (shopifyOk && ordersOk && envOk) {
    console.log(`  ${ok('SHOPIFY LIVE — ready for Phase 2 (Auto-Store)')}`);
    console.log(`  ${C.dim}Next: Activate order automation, Printify fulfillment, support agent${C.reset}`);
    process.exitCode = 0;
  } else {
    console.log(`  ${fail('BLOCKED — fix before Phase 2')}`);
    if (!shopifyOk) console.log(`     → Fix SHOPIFY_STORE_URL and SHOPIFY_ADMIN_TOKEN`);
    if (!ordersOk) console.log(`     → Check token scopes (needs: read_orders, read_products)`);
    if (!envOk) console.log(`     → Add missing keys to .env, replace PLACEHOLDER values`);
    process.exitCode = 1;
  }

  // ── Write .env if requested ─────────────────────────────────
  if (writeEnv && !envOk) {
    console.log(`\n${C.yellow}Writing .env template...${C.reset}`);
    const template = `# RUDIBOT Production ENV — generated by test-live-connections.js
NODE_ENV=production
PORT=3200

# Shopify (REQUIRED for Phase 1)
SHOPIFY_STORE_URL=your-store.myshopify.com
SHOPIFY_ADMIN_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SHOPIFY_API_VERSION=2025-01
SHOPIFY_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SHOPIFY_LOCATION_ID=123456789

# Printify
PRINTIFY_API_KEY=your_printify_key
PRINTIFY_SHOP_ID=123456

# PayPal
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
PAYPAL_SANDBOX=true

# Bank Import
BANK_IMPORT_PATH=./imports/bank

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789

# AI APIs
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
PERPLEXITY_API_KEY=pplx-...
`;
    fs.writeFileSync(path.join(__dirname, '..', '.env.template'), template);
    console.log(`  ${ok('.env.template written to project root')}`);
  }
}

main().catch(err => {
  console.error(fail(`Fatal error: ${err.message}`));
  process.exit(1);
});
