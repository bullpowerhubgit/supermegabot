/**
 * Test orchestrator integration
 */

const http = require('http');

async function testOrchestrator() {
  console.log('🔧 Testing Orchestrator Integration\n');

  const baseUrl = 'http://localhost:3200';

  // Test 1: Health check
  console.log('1. Health Check');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/health`);
    const data = await res.json();
    console.log('✅ Health:', data.service, '| Correlation:', data.correlationId);
  } catch (err) {
    console.log('❌ Health check failed:', err.message);
    return;
  }

  // Test 2: Submit green command (auto-allow)
  console.log('\n2. Green Command (Auto-Allow)');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'test',
        command: 'health_check',
        target: 'system'
      })
    });
    const data = await res.json();
    console.log('✅ Command submitted:', data.result.status, '| Job:', data.job.jobId);
  } catch (err) {
    console.log('❌ Command submission failed:', err.message);
  }

  // Test 3: Submit yellow command (approval required)
  console.log('\n3. Yellow Command (Approval Required)');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'test',
        command: 'security_scan',
        target: 'system'
      })
    });
    const data = await res.json();
    console.log('✅ Command submitted:', data.result.status, '| Approval ID:', data.result.approvalId);
  } catch (err) {
    console.log('❌ Yellow command failed:', err.message);
  }

  // Test 4: Submit red command (blocked)
  console.log('\n4. Red Command (Blocked)');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'test',
        command: 'delete_account',
        target: 'system'
      })
    });
    const data = await res.json();
    console.log('✅ Command submitted:', data.result.status, '| Reason:', data.result.reason);
  } catch (err) {
    console.log('❌ Red command failed:', err.message);
  }

  // Test 5: Event submission
  console.log('\n5. Event Submission');
  try {
    const res = await fetch(`${baseUrl}/orchestrator/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'system',
        eventType: 'daily_report_trigger',
        target: 'system'
      })
    });
    const data = await res.json();
    console.log('✅ Event submitted:', data.status, '| Job:', data.jobId);
  } catch (err) {
    console.log('❌ Event submission failed:', err.message);
  }

  // Test 6: Get queue stats (wait a moment for processing)
  await new Promise(r => setTimeout(r, 2000));
  console.log('\n6. Queue Status');
  try {
    const orchestrator = require('./core/orchestrator').Orchestrator;
    const testOrch = new orchestrator({ logger: console });
    const status = await testOrch.getStatus();
    console.log('✅ Queue stats:', status.stats);
  } catch (err) {
    console.log('❌ Queue status failed:', err.message);
  }

  console.log('\n🎯 Orchestrator integration test completed');
}

// Run test if server is running
async function checkServerAndTest() {
  try {
    const res = await fetch('http://localhost:3200/api/health');
    if (res.ok) {
      console.log('✅ Server is running, starting orchestrator test...\n');
      await testOrchestrator();
    } else {
      console.log('❌ Server responded but not healthy');
    }
  } catch (err) {
    console.log('❌ Server not running. Start with: npm start or node dev/server.js');
  }
}

checkServerAndTest();
