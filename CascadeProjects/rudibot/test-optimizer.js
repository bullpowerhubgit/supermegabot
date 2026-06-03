/**
 * Test Subscription Optimizer Integration
 */

async function testOptimizer() {
  console.log('🔧 Testing Subscription Optimizer\n');

  const baseUrl = 'http://localhost:3000';

  // Test 1: Get all subscriptions
  console.log('1. Get Subscriptions');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/subscriptions`);
    const data = await res.json();
    console.log('✅ Response OK:', data.ok);
    if (data.subscriptions) {
      console.log('   Subscriptions:', data.subscriptions.length);
      console.log('   Total Monthly:', data.totalMonthly, '€');
      data.subscriptions.forEach(sub => {
        console.log(`   - ${sub.name}: ${sub.cost}€`);
      });
    } else {
      console.log('   Raw response:', JSON.stringify(data).substring(0, 200));
    }
  } catch (err) {
    console.log('❌ Failed:', err.message);
  }

  // Test 2: Analyze subscriptions
  console.log('\n2. Analyze Subscriptions');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/subscriptions/analyze`);
    const data = await res.json();
    console.log('✅ Analysis complete');
    if (data.analysis) {
      console.log('   Immediate Cancel:', data.analysis.immediateCancel?.length || 0);
      if (data.analysis.immediateCancel?.length > 0) {
        data.analysis.immediateCancel.forEach(item => {
          console.log(`   ❌ ${item.name} (${item.cost}€): ${item.reason}`);
        });
      }
      console.log('   Consider Cancel:', data.analysis.considerCancel?.length || 0);
      if (data.analysis.considerCancel?.length > 0) {
        data.analysis.considerCancel.forEach(item => {
          console.log(`   ⚠️ ${item.name} (${item.cost}€): ${item.reason}`);
        });
      }
      console.log('   Potential Savings:', data.analysis.potentialSavings, '€/Monat');
    }
  } catch (err) {
    console.log('❌ Failed:', err.message);
  }

  // Test 3: Prepare cancellation
  console.log('\n3. Prepare Cancellation');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/subscriptions/cancel/sub_adobe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'Nicht genutzt seit 85 Tagen' })
    });
    const data = await res.json();
    console.log('✅ Cancellation prepared');
    if (data.cancellation) {
      console.log('   Status:', data.cancellation.status);
      console.log('   Reason:', data.cancellation.reason);
      console.log('   Requires Approval:', data.cancellation.requiresApproval);
    }
  } catch (err) {
    console.log('❌ Failed:', err.message);
  }

  // Test 4: Get reminders
  console.log('\n4. Get Reminders');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/subscriptions/reminders`);
    const data = await res.json();
    console.log('✅ Reminders:', data.reminders?.length || 0);
    if (data.reminders?.length > 0) {
      data.reminders.forEach(rem => {
        console.log(`   ⏰ ${rem.name}: ${rem.action}`);
      });
    }
  } catch (err) {
    console.log('❌ Failed:', err.message);
  }

  console.log('\n🎯 Subscription Optimizer test completed');
}

async function checkServerAndTest() {
  try {
    const res = await fetch('http://localhost:3000/api/health');
    if (res.ok) {
      console.log('✅ Server running, starting optimizer test...\n');
      await testOptimizer();
    } else {
      console.log('❌ Server not healthy');
    }
  } catch (err) {
    console.log('❌ Server not running. Start with: node dev/server.js');
  }
}

checkServerAndTest();
