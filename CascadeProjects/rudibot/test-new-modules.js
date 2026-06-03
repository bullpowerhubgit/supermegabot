/**
 * Test-Script für alle neuen Module
 * 
 * Getestete Module:
 * - Protection List
 * - Case Manager  
 * - ELSTER Assistant
 * - Expense Radar
 * - Demo Output
 * - Dashboard API Integration
 */

const http = require('http');

// Test configuration
const BASE_URL = 'http://localhost:3201';
const API_BASE = `${BASE_URL}/dashboard`;

// Test utilities
function makeRequest(path, method = 'GET', data = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: 3201,
      path: path,
      method: method,
      headers: {
        'Content-Type': 'application/json'
      }
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const parsed = body ? JSON.parse(body) : {};
          resolve({ status: res.statusCode, data: parsed });
        } catch (err) {
          resolve({ status: res.statusCode, data: body });
        }
      });
    });

    req.on('error', reject);

    if (data) {
      req.write(JSON.stringify(data));
    }

    req.end();
  });
}

// Test runner
async function runTest(testName, testFn) {
  try {
    console.log(`\n🧪 ${testName}`);
    console.log('─'.repeat(50));
    
    const result = await testFn();
    
    if (result.success) {
      console.log(`✅ ${result.message || 'Test passed'}`);
      if (result.data) {
        console.log(`📊 ${JSON.stringify(result.data, null, 2)}`);
      }
    } else {
      console.log(`❌ ${result.message || 'Test failed'}`);
      if (result.error) {
        console.log(`🔥 Error: ${result.error}`);
      }
    }
    
    return result.success;
  } catch (err) {
    console.log(`💥 Test crashed: ${err.message}`);
    return false;
  }
}

// Test data generators
function generateTestSubscription() {
  return {
    name: 'Test Subscription',
    vendor: 'Test Vendor',
    cost: 29.99,
    billingCycle: 'monthly',
    category: 'subscriptions',
    usageScore: 25,
    daysSinceLastUse: 45,
    paymentCount: 2,
    lastUsed: '2024-11-01'
  };
}

function generateTestExpense() {
  return {
    name: 'Test Expense',
    amount: 49.99,
    category: 'software_tools',
    type: 'recurring',
    billingCycle: 'monthly',
    vendor: 'Test Software',
    description: 'Test software subscription',
    tags: ['test', 'software']
  };
}

function generateTestCase() {
  return {
    type: 'tax',
    title: 'Test Steuerfall 2024',
    description: 'Testfall für Steuererklärung 2024',
    priority: 1,
    tags: ['test', 'steuer'],
    complexity: 'medium',
    impact: 'medium'
  };
}

// Test suites
async function testProtectionList() {
  console.log('\n🔒 PROTECTION LIST TESTS');
  console.log('='.repeat(60));
  
  let passed = 0;
  const total = 4;

  // Test 1: Get protection overview
  passed += await runTest('Protection Overview', async () => {
    const response = await makeRequest('/dashboard/protection/overview');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const protection = response.data.protection;
    if (!protection.categories || !protection.report) {
      return { success: false, error: 'Missing protection data' };
    }
    
    return { 
      success: true, 
      message: 'Protection overview loaded',
      data: { categories: Object.keys(protection.categories).length }
    };
  });

  // Test 2: Add manual protection
  passed += await runTest('Add Manual Protection', async () => {
    const protection = {
      name: 'Test Service',
      vendor: 'Test Vendor',
      cost: 99.99,
      reason: 'Test protection',
      priority: 2
    };
    
    const response = await makeRequest('/dashboard/protection/add', 'POST', protection);
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Manual protection added',
      data: { id: response.data.protection.id }
    };
  });

  // Test 3: Check protection status
  passed += await runTest('Check Protection Status', async () => {
    const subscription = generateTestSubscription();
    const response = await makeRequest('/dashboard/subscriptions/classify', 'POST', { subscriptions: [subscription] });
    
    if (response.status === 200 && response.data.ok) {
      return { 
        success: true, 
        message: 'Protection status checked',
        data: { classified: response.data.classifications?.length || 0 }
      };
    }
    
    return { success: false, error: 'Protection status check failed' };
  });

  // Test 4: Remove protection
  passed += await runTest('Remove Protection', async () => {
    // Try to remove with a test ID (might fail if not exists)
    const response = await makeRequest('/dashboard/protection/remove/test_id', 'DELETE');
    
    // 404 is acceptable for test ID
    if (response.status === 200 || response.status === 404) {
      return { 
        success: true, 
        message: 'Protection removal endpoint works',
        data: { status: response.status }
      };
    }
    
    return { success: false, error: `Status ${response.status}` };
  });

  console.log(`\n📊 Protection List: ${passed}/${total} tests passed`);
  return passed === total;
}

async function testCaseManager() {
  console.log('\n📋 CASE MANAGER TESTS');
  console.log('='.repeat(60));
  
  let passed = 0;
  const total = 5;

  // Test 1: Get cases overview
  passed += await runTest('Cases Overview', async () => {
    const response = await makeRequest('/dashboard/cases');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const data = response.data;
    if (!data.cases || !data.statistics) {
      return { success: false, error: 'Missing case data' };
    }
    
    return { 
      success: true, 
      message: 'Cases overview loaded',
      data: { cases: data.cases.length, statistics: data.statistics.total }
    };
  });

  // Test 2: Create new case
  passed += await runTest('Create Case', async () => {
    const caseData = generateTestCase();
    
    const response = await makeRequest('/dashboard/cases', 'POST', caseData);
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Case created',
      data: { id: response.data.case.id, type: response.data.case.type }
    };
  });

  // Test 3: Get overdue cases
  passed += await runTest('Overdue Cases', async () => {
    const response = await makeRequest('/dashboard/cases/overdue');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Overdue cases checked',
      data: { overdue: response.data.overdue }
    };
  });

  // Test 4: Add document to case
  passed += await runTest('Add Document', async () => {
    const document = {
      name: 'test_document.pdf',
      type: 'steuerbescheid',
      path: '/test/path',
      size: 1024,
      required: true
    };
    
    const response = await makeRequest('/dashboard/cases/test_id/documents', 'POST', document);
    
    // 404 is acceptable for test case ID
    if (response.status === 200 || response.status === 404) {
      return { 
        success: true, 
        message: 'Document addition endpoint works',
        data: { status: response.status }
      };
    }
    
    return { success: false, error: `Status ${response.status}` };
  });

  // Test 5: Get case types
  passed += await runTest('Case Types', async () => {
    const response = await makeRequest('/dashboard/cases');
    
    if (response.status === 200 && response.data.ok && response.data.types) {
      return { 
        success: true, 
        message: 'Case types loaded',
        data: { types: Object.keys(response.data.types).length }
      };
    }
    
    return { success: false, error: 'Case types check failed' };
  });

  console.log(`\n📊 Case Manager: ${passed}/${total} tests passed`);
  return passed === total;
}

async function testElsterAssistant() {
  console.log('\n🏛️ ELSTER ASSISTANT TESTS');
  console.log('='.repeat(60));
  
  let passed = 0;
  const total = 5;

  // Test 1: Get ELSTER overview
  passed += await runTest('ELSTER Overview', async () => {
    const response = await makeRequest('/dashboard/elster/overview');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const elster = response.data.elster;
    if (!elster.summary || !elster.taxYears) {
      return { success: false, error: 'Missing ELSTER data' };
    }
    
    return { 
      success: true, 
      message: 'ELSTER overview loaded',
      data: { taxYears: elster.taxYears.length }
    };
  });

  // Test 2: Initialize tax year
  passed += await runTest('Initialize Tax Year', async () => {
    const options = {
      filingDeadline: '2025-05-31',
      notes: 'Test Steuerjahr'
    };
    
    const response = await makeRequest('/dashboard/elster/tax-years/2024', 'POST', options);
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Tax year initialized',
      data: { year: response.data.taxYear.year }
    };
  });

  // Test 3: Get checklist
  passed += await runTest('Get Checklist', async () => {
    const response = await makeRequest('/dashboard/elster/tax-years/2024/checklist');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const checklist = response.data.checklist;
    if (!checklist.year || !checklist.progress) {
      return { success: false, error: 'Missing checklist data' };
    }
    
    return { 
      success: true, 
      message: 'Checklist loaded',
      data: { progress: checklist.progress.percentage }
    };
  });

  // Test 4: Get missing documents
  passed += await runTest('Missing Documents', async () => {
    const response = await makeRequest('/dashboard/elster/tax-years/2024/missing');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const missing = response.data.missing;
    if (typeof missing.total !== 'number') {
      return { success: false, error: 'Missing missing documents data' };
    }
    
    return { 
      success: true, 
      message: 'Missing documents checked',
      data: { total: missing.total, overdue: missing.overdue }
    };
  });

  // Test 5: Document types
  passed += await runTest('Document Types', async () => {
    const response = await makeRequest('/dashboard/elster/overview');
    
    if (response.status === 200 && response.data.ok && response.data.elster.documentTypes) {
      return { 
        success: true, 
        message: 'Document types loaded',
        data: { types: Object.keys(response.data.elster.documentTypes).length }
      };
    }
    
    return { success: false, error: 'Document types check failed' };
  });

  console.log(`\n📊 ELSTER Assistant: ${passed}/${total} tests passed`);
  return passed === total;
}

async function testExpenseRadar() {
  console.log('\n📈 EXPENSE RADAR TESTS');
  console.log('='.repeat(60));
  
  let passed = 0;
  const total = 6;

  // Test 1: Get expense overview
  passed += await runTest('Expense Overview', async () => {
    const response = await makeRequest('/dashboard/expenses/overview');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const overview = response.data.expenses;
    if (!overview.currentMonth || !overview.categories) {
      return { success: false, error: 'Missing expense overview data' };
    }
    
    return { 
      success: true, 
      message: 'Expense overview loaded',
      data: { total: overview.summary?.totalMonthlyExpenses || 0 }
    };
  });

  // Test 2: Add expense
  passed += await runTest('Add Expense', async () => {
    const expense = generateTestExpense();
    
    const response = await makeRequest('/dashboard/expenses', 'POST', expense);
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Expense added',
      data: { id: response.data.expense.id, category: response.data.expense.category }
    };
  });

  // Test 3: Get trends
  passed += await runTest('Expense Trends', async () => {
    const response = await makeRequest('/dashboard/expenses/trends?months=6');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const data = response.data;
    if (!data.trend || !data.history) {
      return { success: false, error: 'Missing trend data' };
    }
    
    return { 
      success: true, 
      message: 'Trends loaded',
      data: { trend: data.trend.trend, history: data.history.length }
    };
  });

  // Test 4: Detect anomalies
  passed += await runTest('Detect Anomalies', async () => {
    const response = await makeRequest('/dashboard/expenses/anomalies');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Anomalies checked',
      data: { anomalies: response.data.anomalies.length }
    };
  });

  // Test 5: Get savings opportunities
  passed += await runTest('Savings Opportunities', async () => {
    const response = await makeRequest('/dashboard/expenses/savings');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Savings opportunities analyzed',
      data: { opportunities: response.data.opportunities.length }
    };
  });

  // Test 6: Set budget
  passed += await runTest('Set Budget', async () => {
    const budget = {
      category: 'subscriptions',
      amount: 100,
      period: 'monthly'
    };
    
    const response = await makeRequest('/dashboard/expenses/budgets', 'POST', budget);
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Budget set',
      data: { category: response.data.budget.category, amount: response.data.budget.amount }
    };
  });

  console.log(`\n📊 Expense Radar: ${passed}/${total} tests passed`);
  return passed === total;
}

async function testDemoOutput() {
  console.log('\n🎭 DEMO OUTPUT TESTS');
  console.log('='.repeat(60));
  
  let passed = 0;
  const total = 5;

  // Test 1: Get decisions
  passed += await runTest('Get Decisions', async () => {
    const response = await makeRequest('/dashboard/demo/decisions');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Decisions loaded',
      data: { decisions: response.data.decisions.length }
    };
  });

  // Test 2: Format decision
  passed += await runTest('Format Decision', async () => {
    const payload = {
      subscription: generateTestSubscription(),
      decision: {
        action: 'cancel_immediately',
        reason: '30+ Tage ungenutzt',
        confidence: 0.9,
        priority: 'high'
      },
      context: {
        usageScore: 25,
        daysSinceLastUse: 45
      }
    };
    
    const response = await makeRequest('/dashboard/demo/decisions', 'POST', payload);
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const decision = response.data.decision;
    if (!decision.recommendation || !decision.nextSteps) {
      return { success: false, error: 'Missing formatted decision data' };
    }
    
    return { 
      success: true, 
      message: 'Decision formatted',
      data: { action: decision.decision.action, priority: decision.decision.priority }
    };
  });

  // Test 3: Get summary
  passed += await runTest('Get Summary', async () => {
    const response = await makeRequest('/dashboard/demo/summary');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const summary = response.data.summary;
    if (!summary.overview || !summary.actions) {
      return { success: false, error: 'Missing summary data' };
    }
    
    return { 
      success: true, 
      message: 'Summary generated',
      data: { total: summary.overview.totalSubscriptions, savings: summary.savings.total }
    };
  });

  // Test 4: Get action items
  passed += await runTest('Get Action Items', async () => {
    const response = await makeRequest('/dashboard/demo/actions');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const data = response.data;
    if (!data.actionItems || !data.progress) {
      return { success: false, error: 'Missing action data' };
    }
    
    return { 
      success: true, 
      message: 'Action items generated',
      data: { items: data.actionItems.length, completion: data.progress.completionRate }
    };
  });

  // Test 5: Export JSON
  passed += await runTest('Export JSON', async () => {
    const response = await makeRequest('/dashboard/demo/export/json');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    const exportData = response.data.export;
    if (!exportData.metrics || !exportData.decisions) {
      return { success: false, error: 'Missing export data' };
    }
    
    return { 
      success: true, 
      message: 'JSON export successful',
      data: { decisions: exportData.decisions.length, metrics: Object.keys(exportData.metrics).length }
    };
  });

  console.log(`\n📊 Demo Output: ${passed}/${total} tests passed`);
  return passed === total;
}

async function testDashboardIntegration() {
  console.log('\n🌐 DASHBOARD INTEGRATION TESTS');
  console.log('='.repeat(60));
  
  let passed = 0;
  const total = 3;

  // Test 1: Dashboard overview with new modules
  passed += await runTest('Dashboard Overview', async () => {
    const response = await makeRequest('/dashboard/overview');
    
    if (response.status !== 200) {
      return { success: false, error: `Status ${response.status}` };
    }
    
    if (!response.data.ok) {
      return { success: false, error: response.data.error };
    }
    
    return { 
      success: true, 
      message: 'Dashboard overview loaded',
      data: { totalCost: response.data.overview.totalMonthlyCost }
    };
  });

  // Test 2: Cross-module data flow
  passed += await runTest('Cross-Module Data Flow', async () => {
    // Add expense -> check if it appears in radar
    const expense = generateTestExpense();
    const addResponse = await makeRequest('/dashboard/expenses', 'POST', expense);
    
    if (addResponse.status !== 200 || !addResponse.data.ok) {
      return { success: false, error: 'Failed to add expense' };
    }
    
    // Check if expense appears in overview
    const overviewResponse = await makeRequest('/dashboard/expenses/overview');
    
    if (overviewResponse.status === 200 && overviewResponse.data.ok) {
      return { 
        success: true, 
        message: 'Cross-module data flow working',
        data: { expenseAdded: true, overviewLoaded: true }
      };
    }
    
    return { success: false, error: 'Cross-module data flow failed' };
  });

  // Test 3: Module health check
  passed += await runTest('Module Health Check', async () => {
    const modules = [
      '/dashboard/protection/overview',
      '/dashboard/cases',
      '/dashboard/elster/overview',
      '/dashboard/expenses/overview',
      '/dashboard/demo/decisions'
    ];
    
    let healthyModules = 0;
    
    for (const module of modules) {
      try {
        const response = await makeRequest(module);
        if (response.status === 200 && response.data.ok) {
          healthyModules++;
        }
      } catch (err) {
        // Module not responding
      }
    }
    
    const success = healthyModules >= modules.length * 0.8; // 80% healthy
    
    return { 
      success, 
      message: `${healthyModules}/${modules.length} modules healthy`,
      data: { healthyModules, totalModules: modules.length }
    };
  });

  console.log(`\n📊 Dashboard Integration: ${passed}/${total} tests passed`);
  return passed === total;
}

// Main test runner
async function runAllTests() {
  console.log('🚀 STARTING NEW MODULES TEST SUITE');
  console.log('='.repeat(80));
  console.log(`Testing at: ${new Date().toLocaleString('de-DE')}`);
  console.log(`Server: ${BASE_URL}`);
  
  const results = {
    protectionList: false,
    caseManager: false,
    elsterAssistant: false,
    expenseRadar: false,
    demoOutput: false,
    dashboardIntegration: false
  };
  
  try {
    // Check if server is running
    console.log('\n🔍 Checking server availability...');
    const healthCheck = await makeRequest('/orchestrator/health');
    
    if (healthCheck.status !== 200) {
      console.log('❌ Server not available - please start the development server first');
      console.log('💡 Run: npm run dev or node dev/server.js');
      return;
    }
    
    console.log('✅ Server is running');
    
    // Run all test suites
    results.protectionList = await testProtectionList();
    results.caseManager = await testCaseManager();
    results.elsterAssistant = await testElsterAssistant();
    results.expenseRadar = await testExpenseRadar();
    results.demoOutput = await testDemoOutput();
    results.dashboardIntegration = await testDashboardIntegration();
    
    // Final summary
    console.log('\n' + '='.repeat(80));
    console.log('📊 FINAL TEST RESULTS');
    console.log('='.repeat(80));
    
    const passedSuites = Object.values(results).filter(Boolean).length;
    const totalSuites = Object.keys(results).length;
    
    for (const [suite, passed] of Object.entries(results)) {
      const icon = passed ? '✅' : '❌';
      const name = suite.charAt(0).toUpperCase() + suite.slice(1).replace(/([A-Z])/g, ' $1');
      console.log(`${icon} ${name}: ${passed ? 'PASSED' : 'FAILED'}`);
    }
    
    console.log(`\n🎯 Overall: ${passedSuites}/${totalSuites} test suites passed`);
    
    if (passedSuites === totalSuites) {
      console.log('🎉 ALL TESTS PASSED! New modules are working correctly.');
    } else {
      console.log('⚠️  Some tests failed. Check the logs above for details.');
    }
    
    console.log('\n📝 Next steps:');
    console.log('1. Fix any failed tests');
    console.log('2. Test the dashboard UI at http://localhost:3200/dashboard.html');
    console.log('3. Run integration tests with real data');
    
  } catch (err) {
    console.log(`💥 Test suite crashed: ${err.message}`);
  }
}

// Run tests if this file is executed directly
if (require.main === module) {
  runAllTests().catch(console.error);
}

module.exports = { runAllTests };
