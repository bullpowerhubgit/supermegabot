#!/usr/bin/env node
/**
 * RUDIBOT COMPREHENSIVE API TEST SUITE
 * Tests all 45 API endpoints systematically
 */
require('dotenv').config();
const fetch = require('node-fetch');

const BASE_URL = 'http://localhost:3200';
const results = [];
let serverRunning = false;

// Test configuration
const TEST_CONFIG = {
  timeout: 5000,
  retryCount: 2,
  parallelTests: 5
};

function log(testId, endpoint, method, status, expected, actual, details = '') {
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : status === 'SKIP' ? '⚠️' : '⏸️';
  console.log(`${icon} ${testId.padEnd(3)} | ${method.padEnd(6)} | ${endpoint.padEnd(35)} | ${status.padEnd(6)} | ${details}`);
  results.push({
    testId,
    endpoint,
    method,
    status,
    expected,
    actual,
    details,
    timestamp: new Date().toISOString()
  });
}

async function testEndpoint(testId, endpoint, method = 'GET', body = null, expectedStatus = 200) {
  try {
    const url = `${BASE_URL}${endpoint}`;
    const options = {
      method,
      timeout: TEST_CONFIG.timeout,
      headers: { 'Content-Type': 'application/json' }
    };
    
    if (body) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(url, options);
    const responseData = await response.text();
    
    let actualStatus = response.status;
    let details = '';
    
    // Parse JSON if possible
    let jsonData = null;
    try {
      jsonData = JSON.parse(responseData);
    } catch (e) {
      // Not JSON, keep as text
    }
    
    if (response.status === expectedStatus) {
      if (jsonData && jsonData.error) {
        log(testId, endpoint, method, 'FAIL', expectedStatus, actualStatus, `API Error: ${jsonData.error}`);
        return 'FAIL';
      } else {
        details = jsonData ? `JSON Response (${responseData.length} chars)` : `Text Response (${responseData.length} chars)`;
        log(testId, endpoint, method, 'PASS', expectedStatus, actualStatus, details);
        return 'PASS';
      }
    } else {
      details = jsonData?.error || responseData.substring(0, 50);
      log(testId, endpoint, method, 'FAIL', expectedStatus, actualStatus, details);
      return 'FAIL';
    }
  } catch (error) {
    log(testId, endpoint, method, 'FAIL', expectedStatus, 'ERROR', error.message);
    return 'FAIL';
  }
}

async function checkServerHealth() {
  console.log('\n🔍 Checking server health...');
  try {
    const response = await fetch(`${BASE_URL}/api/health`, { timeout: 3000 });
    if (response.ok) {
      serverRunning = true;
      console.log('✅ Server is running');
      return true;
    } else {
      console.log('❌ Server returned error:', response.status);
      return false;
    }
  } catch (error) {
    console.log('❌ Server not accessible:', error.message);
    console.log('💡 Start server with: node server.js');
    return false;
  }
}

async function runCoreTests() {
  console.log('\n🧪 CORE ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('001', '/', 'GET');
  await testEndpoint('002', '/health', 'GET');
  await testEndpoint('003', '/api/health', 'GET');
  await testEndpoint('004', '/api/status', 'GET');
  await testEndpoint('005', '/nonexistent', 'GET', null, 404);
}

async function runShopifyTests() {
  console.log('\n🛒 SHOPIFY ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('006', '/api/shopify/store', 'GET');
  await testEndpoint('007', '/api/shopify/products', 'GET');
  await testEndpoint('008', '/api/shopify/orders', 'GET');
  await testEndpoint('009', '/api/shopify/customers', 'GET');
  await testEndpoint('010', '/api/shopify/inventory', 'GET');
  await testEndpoint('011', '/api/shopify/graphql', 'POST', { query: '{ shop { name } }' });
}

async function runGitHubTests() {
  console.log('\n🐙 GITHUB ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('012', '/api/github/repos', 'GET');
  await testEndpoint('013', '/api/github/repos/nonexistent', 'GET', null, 500);
  await testEndpoint('014', '/api/github/repos', 'POST', { name: 'test-repo' }, 500);
}

async function runAITests() {
  console.log('\n🤖 AI ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('015', '/api/ai/claude', 'POST', { prompt: 'Hello' });
  await testEndpoint('016', '/api/ai/openai', 'POST', { prompt: 'Hello' });
  await testEndpoint('017', '/api/ai/perplexity', 'POST', { query: 'Hello' });
  await testEndpoint('018', '/api/ai/gemini', 'POST', { prompt: 'Hello' });
  await testEndpoint('019', '/api/ai/claude', 'POST', {}, 400); // Missing prompt
}

async function runCommunicationTests() {
  console.log('\n📡 COMMUNICATION ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('020', '/api/telegram/status', 'GET');
  await testEndpoint('021', '/api/telegram/send', 'POST', { chat_id: '123', text: 'Test' });
  await testEndpoint('022', '/api/email/send', 'POST', { to: 'test@example.com', subject: 'Test', text: 'Test' });
  await testEndpoint('023', '/api/whatsapp/webhook', 'GET');
  await testEndpoint('024', '/api/discord/info', 'GET');
  await testEndpoint('025', '/api/twitter/me', 'GET');
  await testEndpoint('026', '/api/instagram/me', 'GET');
}

async function runDatabaseTests() {
  console.log('\n🗄️ DATABASE ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('027', '/api/supabase/test', 'GET');
  await testEndpoint('028', '/api/supabase/test', 'POST', { name: 'test' });
  await testEndpoint('029', '/api/notion/database', 'GET');
  await testEndpoint('030', '/api/notion/page', 'POST', { title: 'Test' });
}

async function runEcommerceTests() {
  console.log('\n🛍️ E-COMMERCE ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('031', '/api/printify/shops', 'GET');
  await testEndpoint('032', '/api/printify/products', 'GET');
  await testEndpoint('033', '/api/digistore/products', 'GET');
  await testEndpoint('034', '/api/digistore/orders', 'GET');
  await testEndpoint('035', '/api/digistore/stats', 'GET');
  await testEndpoint('036', '/api/stripe/balance', 'GET');
}

async function runMediaTests() {
  console.log('\n📺 MEDIA ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('037', '/api/youtube/channel', 'GET');
  await testEndpoint('038', '/api/klaviyo/profiles', 'GET');
  await testEndpoint('039', '/api/mailchimp/lists', 'GET');
}

async function runWebhookTests() {
  console.log('\n🔔 WEBHOOK ENDPOINTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('040', '/webhook', 'POST', { test: 'data' });
  await testEndpoint('041', '/webhooks/shopify/test', 'POST', { test: 'data' });
  await testEndpoint('042', '/webhooks/digistore24/test', 'POST', { test: 'data' });
}

async function runErrorTests() {
  console.log('\n❌ ERROR HANDLING TESTS');
  console.log('ID   | Method | Endpoint                           | Status | Details');
  console.log('-----|--------|-------------------------------------|--------|---------');
  
  await testEndpoint('043', '/invalid-json', 'POST', 'invalid-json', 400);
  await testEndpoint('044', '/api/ai/claude', 'POST', {}, 400); // Missing required field
  await testEndpoint('045', '/api/telegram/send', 'POST', {}, 400); // Missing required fields
}

async function generateReport() {
  const total = results.length;
  const passed = results.filter(r => r.status === 'PASS').length;
  const failed = results.filter(r => r.status === 'FAIL').length;
  const skipped = results.filter(r => r.status === 'SKIP').length;
  
  console.log('\n' + '='.repeat(80));
  console.log('📊 QA TEST REPORT SUMMARY');
  console.log('='.repeat(80));
  console.log(`Total Tests: ${total}`);
  console.log(`✅ Passed: ${passed}`);
  console.log(`❌ Failed: ${failed}`);
  console.log(`⚠️  Skipped: ${skipped}`);
  console.log(`📈 Success Rate: ${((passed/total)*100).toFixed(1)}%`);
  
  if (failed > 0) {
    console.log('\n❌ FAILED TESTS:');
    results.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`   ${r.testId}: ${r.method} ${r.endpoint} - ${r.details}`);
    });
  }
  
  // Critical issues
  const criticalFailures = results.filter(r => 
    r.status === 'FAIL' && 
    (r.actual === 'ERROR' || r.actual >= 500)
  );
  
  if (criticalFailures.length > 0) {
    console.log('\n🚨 CRITICAL ISSUES:');
    criticalFailures.forEach(r => {
      console.log(`   ${r.testId}: ${r.method} ${r.endpoint} - ${r.details}`);
    });
  }
  
  // Service status
  console.log('\n🔧 SERVICE STATUS:');
  const serviceTests = {
    'Server': results.find(r => r.endpoint === '/api/health'),
    'Shopify': results.find(r => r.endpoint === '/api/shopify/store'),
    'GitHub': results.find(r => r.endpoint === '/api/github/repos'),
    'Claude AI': results.find(r => r.endpoint === '/api/ai/claude'),
    'Telegram': results.find(r => r.endpoint === '/api/telegram/status'),
    'Supabase': results.find(r => r.endpoint === '/api/supabase/test')
  };
  
  Object.entries(serviceTests).forEach(([service, test]) => {
    if (test) {
      const icon = test.status === 'PASS' ? '✅' : test.status === 'FAIL' ? '❌' : '⚠️';
      console.log(`   ${icon} ${service}: ${test.status}`);
    } else {
      console.log(`   ❓ ${service}: Not tested`);
    }
  });
  
  console.log('\n' + '='.repeat(80));
  
  // Write detailed report
  const reportData = {
    timestamp: new Date().toISOString(),
    summary: { total, passed, failed, skipped, successRate: (passed/total)*100 },
    criticalFailures: criticalFailures.length,
    results,
    serverRunning
  };
  
  require('fs').writeFileSync('qa-test-results.json', JSON.stringify(reportData, null, 2));
  console.log('📄 Detailed report saved to: qa-test-results.json');
  
  return reportData;
}

// Main execution
async function main() {
  console.log('🚀 RUDIBOT COMPREHENSIVE API TEST SUITE');
  console.log('='.repeat(50));
  
  if (!await checkServerHealth()) {
    process.exit(1);
  }
  
  await runCoreTests();
  await runShopifyTests();
  await runGitHubTests();
  await runAITests();
  await runCommunicationTests();
  await runDatabaseTests();
  await runEcommerceTests();
  await runMediaTests();
  await runWebhookTests();
  await runErrorTests();
  
  const report = await generateReport();
  
  // Exit with appropriate code
  process.exit(report.criticalFailures > 0 ? 1 : 0);
}

if (require.main === module) {
  main().catch(console.error);
}

module.exports = { testEndpoint, generateReport };
