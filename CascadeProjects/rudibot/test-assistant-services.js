/**
 * Test Assistant Service and Cost Monitor Service integration
 */

const http = require('http');

async function testAssistantServices() {
  console.log('🔧 Testing Assistant Services Integration\n');

  const baseUrl = 'http://localhost:3000';

  // Test 1: Assistant Help
  console.log('1. Assistant Help Endpoint');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/assistant/help`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: 'How do I optimize my costs?',
        context: { page: 'dashboard', user: 'admin' }
      })
    });
    const data = await res.json();
    console.log('✅ Assistant Help:', data.ok ? 'Working' : 'Failed');
    if (data.ok) {
      console.log('   Response:', data.response);
      console.log('   Suggestions:', data.suggestions.length);
    }
  } catch (err) {
    console.log('❌ Assistant Help failed:', err.message);
  }

  // Test 2: Form Validation
  console.log('\n2. Form Validation');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/assistant/validate-form`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        data: {
          company: 'Test GmbH',
          amount: '19,99',
          date: '2026-06-03'
          // Missing required fields
        },
        templateType: 'invoice'
      })
    });
    const data = await res.json();
    console.log('✅ Form Validation:', data.ok ? 'Working' : 'Failed');
    if (data.ok) {
      console.log('   Warnings:', data.validation.warnings.length);
      console.log('   Risk Level:', data.validation.risk_level);
      console.log('   Autofill:', Object.keys(data.validation.autofill).length);
    }
  } catch (err) {
    console.log('❌ Form Validation failed:', err.message);
  }

  // Test 3: Assistant Suggestions
  console.log('\n3. Assistant Suggestions');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/assistant/suggest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context: {
          current_page: 'dashboard',
          user_action: 'viewing_costs'
        }
      })
    });
    const data = await res.json();
    console.log('✅ Assistant Suggestions:', data.ok ? 'Working' : 'Failed');
    if (data.ok) {
      console.log('   Immediate:', data.suggestions.immediate.length);
      console.log('   Proactive:', data.suggestions.proactive.length);
      console.log('   Optimization:', data.suggestions.optimization.length);
    }
  } catch (err) {
    console.log('❌ Assistant Suggestions failed:', err.message);
  }

  // Test 4: Revenue Dashboard
  console.log('\n4. Revenue Dashboard');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/dashboard/revenue`);
    const data = await res.json();
    console.log('✅ Revenue Dashboard:', data.ok ? 'Working' : 'Failed');
    if (data.ok) {
      console.log('   Today Revenue:', data.revenue.today);
      console.log('   7-Day Total:', data.revenue.last7Days.total);
      console.log('   Growth:', data.revenue.last7Days.growth + '%');
    }
  } catch (err) {
    console.log('❌ Revenue Dashboard failed:', err.message);
  }

  // Test 5: Costs Dashboard
  console.log('\n5. Costs Dashboard');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/dashboard/costs`);
    const data = await res.json();
    console.log('✅ Costs Dashboard:', data.ok ? 'Working' : 'Failed');
    if (data.ok) {
      console.log('   Total Costs:', data.costs.grandTotal);
      console.log('   Categories:', data.costs.breakdown.length);
      console.log('   Alerts:', data.costs.alerts.length);
    }
  } catch (err) {
    console.log('❌ Costs Dashboard failed:', err.message);
  }

  // Test 6: Business Health
  console.log('\n6. Business Health');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/dashboard/health`);
    const data = await res.json();
    console.log('✅ Business Health:', data.ok ? 'Working' : 'Failed');
    if (data.ok) {
      console.log('   Health Score:', data.health.score);
      console.log('   Status:', data.health.status);
      console.log('   Profit Margin:', data.health.metrics.profitMargin + '%');
      console.log('   Recommendations:', data.health.recommendations.length);
    }
  } catch (err) {
    console.log('❌ Business Health failed:', err.message);
  }

  console.log('\n🎯 Assistant Services integration test completed');
}

// Run test if server is running
async function checkServerAndTest() {
  try {
    const res = await fetch('http://localhost:3000/api/health');
    if (res.ok) {
      console.log('✅ Server is running, starting assistant services test...\n');
      await testAssistantServices();
    } else {
      console.log('❌ Server responded but not healthy');
    }
  } catch (err) {
    console.log('❌ Server not running. Start with: npm start or node dev/server.js');
  }
}

checkServerAndTest();
