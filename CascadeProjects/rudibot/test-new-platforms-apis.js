#!/usr/bin/env node
/**
 * Test Script for New Platform APIs
 * Tests all newly added platform APIs: Pinterest, Reddit, Twitter, LinkedIn, Upwork, Etsy, Gumroad, Product Hunt, Udemy, Notion, Airtable
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
    const timer = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timer);
    const data = await res.json().catch(() => null);
    if (res.ok) return { ok: true, data };
    return { ok: false, error: data?.error?.message || `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

// Pinterest Tests
async function testPinterest() {
  const token = process.env.PINTEREST_ACCESS_TOKEN;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('Pinterest', 'SKIP', 'No API key');
  
  const r = await testAPI('Pinterest', 'https://api.pinterest.com/v5/user_account', {
    'Authorization': `Bearer ${token}`
  });
  log('Pinterest', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Reddit Tests
async function testReddit() {
  const clientId = process.env.REDDIT_CLIENT_ID;
  const clientSecret = process.env.REDDIT_CLIENT_SECRET;
  if (!clientId || !clientSecret) return log('Reddit', 'SKIP', 'No API keys');
  
  try {
    const auth = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');
    const tokenRes = await fetch('https://www.reddit.com/api/v1/access_token', {
      method: 'POST',
      headers: { 
        'Authorization': `Basic ${auth}`, 
        'Content-Type': 'application/x-www-form-urlencoded', 
        'User-Agent': 'RudiBot/1.0' 
      },
      body: 'grant_type=client_credentials'
    });
    const tokenData = await tokenRes.json();
    if (tokenData.access_token) {
      log('Reddit', 'OK', 'OAuth successful');
    } else {
      log('Reddit', 'FAIL', 'OAuth failed');
    }
  } catch (e) {
    log('Reddit', 'FAIL', e.message);
  }
}

// Twitter/X Tests
async function testTwitter() {
  const token = process.env.TWITTER_BEARER_TOKEN;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('Twitter/X', 'SKIP', 'No API key');
  
  const r = await testAPI('Twitter/X', 'https://api.x.com/2/users/me', {
    'Authorization': `Bearer ${token}`
  });
  log('Twitter/X', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// LinkedIn Tests
async function testLinkedIn() {
  const token = process.env.LINKEDIN_ACCESS_TOKEN;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('LinkedIn', 'SKIP', 'No API key');
  
  const r = await testAPI('LinkedIn', 'https://api.linkedin.com/v2/me', {
    'Authorization': `Bearer ${token}`
  });
  log('LinkedIn', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Upwork Tests
async function testUpwork() {
  const consumerKey = process.env.UPWORK_CONSUMER_KEY;
  const consumerSecret = process.env.UPWORK_CONSUMER_SECRET;
  const accessToken = process.env.UPWORK_ACCESS_TOKEN;
  const accessSecret = process.env.UPWORK_ACCESS_SECRET;
  
  if (!consumerKey || !consumerSecret || !accessToken || !accessSecret) {
    return log('Upwork', 'SKIP', 'OAuth credentials incomplete');
  }
  
  try {
    const OAuth = require('oauth').OAuth;
    const oa = new OAuth(
      'https://www.upwork.com/api/auth/v1/oauth/token/request',
      'https://www.upwork.com/api/auth/v1/oauth/token/access',
      consumerKey, consumerSecret, '1.0', null, 'HMAC-SHA1'
    );
    
    const data = await new Promise((resolve, reject) => {
      oa.get('https://www.upwork.com/api/profiles/v1/me.json', accessToken, accessSecret,
        (err, data) => err ? reject(err) : resolve(JSON.parse(data))
      );
    });
    log('Upwork', 'OK', 'OAuth successful');
  } catch (e) {
    log('Upwork', 'FAIL', e.message);
  }
}

// Etsy Tests
async function testEtsy() {
  const apiKey = process.env.ETSY_API_KEY;
  if (!apiKey || apiKey.includes('DEIN') || apiKey.includes('HERE')) return log('Etsy', 'SKIP', 'No API key');
  
  const r = await testAPI('Etsy', 'https://openapi.etsy.com/v3/application/ping', {
    'x-api-key': apiKey
  });
  log('Etsy', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Gumroad Tests
async function testGumroad() {
  const token = process.env.GUMROAD_ACCESS_TOKEN;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('Gumroad', 'SKIP', 'No API key');
  
  const r = await testAPI('Gumroad', `https://api.gumroad.com/v2/user?access_token=${token}`);
  log('Gumroad', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Product Hunt Tests
async function testProductHunt() {
  const token = process.env.PRODUCT_HUNT_TOKEN;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('Product Hunt', 'SKIP', 'No API key');
  
  const query = `
    query {
      posts(first: 1, order: RANKING) {
        edges {
          node {
            id
            name
          }
        }
      }
    }
  `;
  
  const r = await testAPI('Product Hunt', 'https://api.producthunt.com/v2/api/graphql', {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }, { query }, 'POST');
  
  log('Product Hunt', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Udemy Tests
async function testUdemy() {
  const token = process.env.UDEMY_API_KEY;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('Udemy', 'SKIP', 'No API key');
  
  const r = await testAPI('Udemy', 'https://www.udemy.com/api-2.0/courses/?page=1&page_size=1', {
    'Authorization': `Basic ${Buffer.from(token + ':').toString('base64')}`
  });
  log('Udemy', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Notion Tests
async function testNotion() {
  const token = process.env.NOTION_API_KEY;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('Notion', 'SKIP', 'No API key');
  
  const r = await testAPI('Notion', 'https://api.notion.com/v1/databases', {
    'Authorization': `Bearer ${token}`,
    'Notion-Version': '2022-06-28'
  });
  log('Notion', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Airtable Tests
async function testAirtable() {
  const token = process.env.AIRTABLE_API_KEY;
  if (!token || token.includes('DEIN') || token.includes('HERE')) return log('Airtable', 'SKIP', 'No API key');
  
  const r = await testAPI('Airtable', 'https://api.airtable.com/v0/meta/bases', {
    'Authorization': `Bearer ${token}`
  });
  log('Airtable', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
}

// Main execution
async function main() {
  console.log('🚀 Testing New Platform APIs...\n');
  
  await testPinterest();
  await testReddit();
  await testTwitter();
  await testLinkedIn();
  await testUpwork();
  await testEtsy();
  await testGumroad();
  await testProductHunt();
  await testUdemy();
  await testNotion();
  await testAirtable();
  
  // Summary
  const ok = results.filter(r => r.status === 'OK').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  const skip = results.filter(r => r.status === 'SKIP').length;
  
  console.log('\n📊 SUMMARY');
  console.log(`✅ Working: ${ok}`);
  console.log(`❌ Failed: ${fail}`);
  console.log(`⚠️ Skipped: ${skip}`);
  console.log(`📈 Success Rate: ${ok > 0 ? Math.round((ok / (ok + fail)) * 100) : 0}%`);
  
  if (fail > 0) {
    console.log('\n❌ Failed APIs:');
    results.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`  - ${r.category}: ${r.message}`);
    });
  }
  
  if (skip > 0) {
    console.log('\n⚠️ Skipped APIs (no keys):');
    results.filter(r => r.status === 'SKIP').forEach(r => {
      console.log(`  - ${r.category}`);
    });
  }
}

main().catch(console.error);
