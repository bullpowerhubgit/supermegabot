/**
 * Test Dashboard Integration — Alle 5 Module
 */

const baseUrl = 'http://localhost:3000';

async function testDashboard() {
  console.log('🔧 Dashboard Integration Test\n');

  const tests = [
    // 1. Overview
    { name: 'Dashboard Overview', method: 'GET', url: '/dashboard/overview' },
    
    // 2. KPIs
    { name: 'Dashboard KPIs', method: 'GET', url: '/dashboard/kpis' },
    
    // 3. Subscriptions
    { name: 'All Subscriptions', method: 'GET', url: '/dashboard/subscriptions' },
    
    // 4. Classified
    { name: 'Classified Subscriptions', method: 'GET', url: '/dashboard/subscriptions/classified' },
    
    // 5. Savings Report
    { name: 'Savings Report', method: 'GET', url: '/dashboard/reports/savings' },
    
    // 6. Analysis
    { name: 'Full Analysis', method: 'GET', url: '/dashboard/analysis' },
    
    // 7. Settings
    { name: 'Settings', method: 'GET', url: '/dashboard/settings' },
    
    // 8. Assistant Optimize
    { name: 'Assistant Optimize', method: 'POST', url: '/dashboard/assistant/optimize-costs' },
    
    // 9. Cancellations
    { name: 'Cancellations Log', method: 'GET', url: '/dashboard/cancellations' },
    
    // 10. Reminders
    { name: 'Reminders', method: 'GET', url: '/orchestrator/subscriptions/reminders' }
  ];

  let passed = 0;
  let failed = 0;

  for (const test of tests) {
    try {
      const options = { method: test.method };
      if (test.method === 'POST') {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify({});
      }
      
      const res = await fetch(`${baseUrl}${test.url}`, options);
      const data = await res.json();
      
      if (data.ok || data.success) {
        console.log(`✅ ${test.name}`);
        passed++;
      } else {
        console.log(`⚠️  ${test.name} — Response ok but data.ok=false`);
        failed++;
      }
    } catch (err) {
      console.log(`❌ ${test.name} — ${err.message}`);
      failed++;
    }
  }

  console.log(`\n📊 Results: ${passed}/${tests.length} passed, ${failed} failed`);
  
  // Summary
  if (failed === 0) {
    console.log('\n🎯 ALL DASHBOARD MODULES INTEGRATED SUCCESSFULLY!');
  }
}

async function checkAndTest() {
  try {
    const res = await fetch(`${baseUrl}/api/health`);
    if (res.ok) {
      await testDashboard();
    } else {
      console.log('❌ Server not healthy');
    }
  } catch (err) {
    console.log('❌ Server not running. Start with: node dev/server.js');
  }
}

checkAndTest();
