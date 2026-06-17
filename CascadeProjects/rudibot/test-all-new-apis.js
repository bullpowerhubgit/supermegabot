// Comprehensive API Test Script for All New APIs
require('dotenv').config();

console.log('═══════════════════════════════════════════');
console.log('  RUDIBOT - ALL NEW APIs TEST');
console.log('═══════════════════════════════════════════');

const baseUrl = 'http://localhost:3200';
const apis = [
  {
    name: 'WhatsApp Business',
    endpoints: [
      { method: 'POST', path: '/api/whatsapp/send', body: { to: '1234567890', message: 'Test message' } }
    ],
    envVars: ['WHATSAPP_PHONE_ID', 'WHATSAPP_ACCESS_TOKEN', 'WHATSAPP_WEBHOOK_VERIFY_TOKEN']
  },
  {
    name: 'Discord Bot',
    endpoints: [
      { method: 'GET', path: '/api/discord/info' }
    ],
    envVars: ['DISCORD_BOT_TOKEN']
  },
  {
    name: 'Twitter/X API v2',
    endpoints: [
      { method: 'GET', path: '/api/twitter/me' },
      { method: 'POST', path: '/api/twitter/tweet', body: { text: 'Test tweet from RudiBot' } }
    ],
    envVars: ['TWITTER_BEARER_TOKEN']
  },
  {
    name: 'Instagram Basic Display',
    endpoints: [
      { method: 'GET', path: '/api/instagram/me' }
    ],
    envVars: ['INSTAGRAM_ACCESS_TOKEN']
  },
  {
    name: 'Notion API',
    endpoints: [
      { method: 'GET', path: '/api/notion/database' },
      { method: 'POST', path: '/api/notion/page', body: { title: 'Test Page', content: 'Test content' } }
    ],
    envVars: ['NOTION_API_KEY', 'NOTION_DATABASE_ID']
  }
];

async function testAPI(api) {
  console.log(`\n🔍 Testing ${api.name}...`);
  
  // Check environment variables
  const missingVars = api.envVars.filter(varName => {
    const value = process.env[varName];
    return !value || value.includes('PLACEHOLDER');
  });
  
  if (missingVars.length > 0) {
    console.log(`⚠️  Missing env vars: ${missingVars.join(', ')}`);
    console.log(`📝 Please configure: https://github.com/rudibot/docs#${api.name.toLowerCase().replace(/\s+/g, '-')}`);
    return { success: false, reason: 'Missing configuration' };
  }
  
  // Test endpoints
  let successCount = 0;
  const results = [];
  
  for (const endpoint of api.endpoints) {
    try {
      const url = `${baseUrl}${endpoint.path}`;
      const options = {
        method: endpoint.method,
        headers: { 'Content-Type': 'application/json' }
      };
      
      if (endpoint.body) {
        options.body = JSON.stringify(endpoint.body);
      }
      
      const response = await fetch(url, options);
      const data = await response.json();
      
      if (response.ok && data.success) {
        console.log(`✅ ${endpoint.method} ${endpoint.path} - SUCCESS`);
        successCount++;
        results.push({ endpoint: endpoint.path, status: 'success', data });
      } else {
        console.log(`❌ ${endpoint.method} ${endpoint.path} - FAILED: ${data.error || response.statusText}`);
        results.push({ endpoint: endpoint.path, status: 'failed', error: data.error || response.statusText });
      }
    } catch (error) {
      console.log(`❌ ${endpoint.method} ${endpoint.path} - ERROR: ${error.message}`);
      results.push({ endpoint: endpoint.path, status: 'error', error: error.message });
    }
  }
  
  const overallSuccess = successCount === api.endpoints.length;
  console.log(`${overallSuccess ? '✅' : '❌'} ${api.name}: ${successCount}/${api.endpoints.length} endpoints working`);
  
  return { success: overallSuccess, results };
}

async function testAllAPIs() {
  console.log('📡 Testing all new APIs...');
  console.log('🌐 Make sure server is running on port 3200');
  
  const results = [];
  
  for (const api of apis) {
    const result = await testAPI(api);
    results.push({ name: api.name, ...result });
  }
  
  // Summary
  console.log('\n═══════════════════════════════════════════');
  console.log('  SUMMARY');
  console.log('═══════════════════════════════════════════');
  
  const workingAPIs = results.filter(r => r.success).length;
  const totalAPIs = results.length;
  
  console.log(`📊 Overall: ${workingAPIs}/${totalAPIs} APIs working (${Math.round(workingAPIs/totalAPIs*100)}%)`);
  
  results.forEach(result => {
    const status = result.success ? '✅' : '❌';
    console.log(`${status} ${result.name}`);
  });
  
  if (workingAPIs === totalAPIs) {
    console.log('\n🎉 ALL NEW APIs ARE WORKING!');
  } else {
    console.log('\n📋 Next steps:');
    console.log('1. Configure missing API keys in .env');
    console.log('2. Follow setup guides in documentation');
    console.log('3. Run this test again');
  }
  
  console.log('\n📚 Documentation:');
  console.log('- NOTION_INTEGRATION.md');
  console.log('- ADDITIONAL_APIS.md');
  console.log('- API_KEYS_GUIDE.md');
  
  return results;
}

// Check if server is running
async function checkServer() {
  try {
    const response = await fetch(`${baseUrl}/api/health`);
    return response.ok;
  } catch (error) {
    console.log('❌ Server not running on port 3200');
    console.log('📝 Start server with: node server.js');
    return false;
  }
}

// Main execution
async function main() {
  const serverRunning = await checkServer();
  if (!serverRunning) {
    process.exit(1);
  }
  
  await testAllAPIs();
}

main().catch(console.error);
