/**
 * Test alle 8 operativen Module
 * 
 * Module:
 * 1. Bank-Importer
 * 2. PayPal-Importer
 * 3. Invoice Hunter
 * 4. Browser Cancel Agent
 * 5. Subscription Classifier (Kill/Downgrade/Keep/Protected)
 * 6. Dashboard API
 * 7. Reminder/Fristenlogik
 * 8. Orchestrator Integration
 */

const baseUrl = 'http://localhost:3000';

async function testModule(name, tests) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`📦 ${name}`);
  console.log(`${'='.repeat(60)}`);
  
  let passed = 0;
  let failed = 0;
  
  for (const test of tests) {
    try {
      const options = { method: test.method || 'GET' };
      if (test.body) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(test.body);
      }
      
      const res = await fetch(`${baseUrl}${test.url}`, options);
      const data = await res.json();
      
      if (data.ok || data.success) {
        console.log(`✅ ${test.name}`);
        if (test.showField && data[test.showField]) {
          console.log(`   ${JSON.stringify(data[test.showField]).substring(0, 150)}`);
        }
        passed++;
      } else {
        console.log(`⚠️  ${test.name} — ok=false`);
        failed++;
      }
    } catch (err) {
      console.log(`❌ ${test.name} — ${err.message}`);
      failed++;
    }
  }
  
  console.log(`\n   ${passed}/${tests.length} passed, ${failed} failed`);
  return { passed, failed, total: tests.length };
}

async function runAllTests() {
  console.log('🧪 TESTING ALL 8 OPERATIVE MODULES');
  console.log(`${'='.repeat(60)}`);

  let totalPassed = 0;
  let totalFailed = 0;

  // 1. Bank Importer
  const bankResult = await testModule('1. BANK IMPORTER', [
    { name: 'Import CSV (Demo)', url: '/dashboard/import/bank', method: 'POST', body: { filePath: '/tmp/demo-bank.csv', format: 'auto' } },
  ]);
  totalPassed += bankResult.passed;
  totalFailed += bankResult.failed;

  // 2. PayPal Importer
  const paypalResult = await testModule('2. PAYPAL IMPORTER', [
    { name: 'Import CSV (Demo)', url: '/dashboard/import/paypal', method: 'POST', body: { filePath: '/tmp/demo-paypal.csv' } },
  ]);
  totalPassed += paypalResult.passed;
  totalFailed += paypalResult.failed;

  // 3. Invoice Hunter
  const invoiceResult = await testModule('3. INVOICE HUNTER', [
    { name: 'Get Invoices', url: '/dashboard/invoices' },
    { name: 'Get Deadlines', url: '/dashboard/invoices/deadlines' },
    { name: 'Parse Invoice Text', url: '/dashboard/invoices/parse', method: 'POST', body: { 
      text: 'Rechnung Nr. 12345\nVon: Adobe Systems\nBetrag: 29,99 EUR\nDatum: 03.06.2026\nKündigungsfrist: 1 Monat zum Monatsende',
      source: 'test'
    }},
  ]);
  totalPassed += invoiceResult.passed;
  totalFailed += invoiceResult.failed;

  // 4. Browser Cancel Agent
  const cancelResult = await testModule('4. BROWSER CANCEL AGENT', [
    { name: 'Get Cancellations', url: '/dashboard/cancellations' },
    { name: 'Prepare Cancellation', url: '/dashboard/cancellations/prepare', method: 'POST', body: { subscriptionId: 'sub_adobe' } },
  ]);
  totalPassed += cancelResult.passed;
  totalFailed += cancelResult.failed;

  // 5. Subscription Classifier
  const classifierResult = await testModule('5. SUBSCRIPTION CLASSIFIER (Kill/Downgrade/Keep/Protected)', [
    { name: 'Classified Subscriptions', url: '/dashboard/subscriptions/classified', showField: 'summary' },
    { name: 'Savings Report', url: '/dashboard/reports/savings', showField: 'savings' },
  ]);
  totalPassed += classifierResult.passed;
  totalFailed += classifierResult.failed;

  // 6. Dashboard API
  const dashboardResult = await testModule('6. DASHBOARD API', [
    { name: 'Overview', url: '/dashboard/overview' },
    { name: 'KPIs', url: '/dashboard/kpis' },
    { name: 'Analysis', url: '/dashboard/analysis' },
    { name: 'Assistant Optimize', url: '/dashboard/assistant/optimize-costs', method: 'POST' },
  ]);
  totalPassed += dashboardResult.passed;
  totalFailed += dashboardResult.failed;

  // 7. Reminder/Fristenlogik
  const reminderResult = await testModule('7. REMINDER / FRISTENLOGIK', [
    { name: 'Get Reminders', url: '/dashboard/reminders' },
    { name: 'Add Custom Reminder', url: '/dashboard/reminders/add', method: 'POST', body: {
      type: 'cancellation_deadline',
      title: 'Test Kündigungsfrist',
      deadline: '2026-12-31',
      details: { subscription: 'Test Abo' }
    }},
  ]);
  totalPassed += reminderResult.passed;
  totalFailed += reminderResult.failed;

  // 8. Orchestrator Integration
  const orchResult = await testModule('8. ORCHESTRATOR INTEGRATION', [
    { name: 'Health Check', url: '/api/health' },
    { name: 'Subscriptions', url: '/orchestrator/subscriptions' },
    { name: 'Analyze', url: '/orchestrator/subscriptions/analyze' },
    { name: 'Reminders', url: '/orchestrator/subscriptions/reminders' },
  ]);
  totalPassed += orchResult.passed;
  totalFailed += orchResult.failed;

  // SUMMARY
  console.log(`\n${'='.repeat(60)}`);
  console.log('📊 GESAMT-ERGEBNIS');
  console.log(`${'='.repeat(60)}`);
  console.log(`✅ Bestanden: ${totalPassed}`);
  console.log(`❌ Fehlgeschlagen: ${totalFailed}`);
  console.log(`📈 Gesamt: ${totalPassed + totalFailed}`);
  console.log(`🎯 Quote: ${((totalPassed / (totalPassed + totalFailed)) * 100).toFixed(0)}%`);
  
  if (totalFailed === 0) {
    console.log(`\n🎉 ALLE 8 MODULE FUNKTIONIEREN!`);
  }
}

async function checkAndRun() {
  try {
    const res = await fetch(`${baseUrl}/api/health`);
    if (res.ok) {
      await runAllTests();
    } else {
      console.log('❌ Server not healthy');
    }
  } catch (err) {
    console.log('❌ Server nicht erreichbar. Starte mit: node dev/server.js');
  }
}

checkAndRun();
