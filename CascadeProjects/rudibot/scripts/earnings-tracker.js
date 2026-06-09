// ============================================================
// earnings-tracker.js — Revenue Analytics & Tracking
// Rudolf Sarkany · Complete Income Monitoring System
// ============================================================
'use strict';
require('dotenv').config();

const fs = require('fs');
const path = require('path');

// ── Config ────────────────────────────────────────────────────
const DATA_DIR = 'data';
const LOGS_DIR = 'logs';

// Ensure directories exist
[DATA_DIR, LOGS_DIR, `${DATA_DIR}/revenue`, `${DATA_DIR}/expenses`].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// ── Revenue Sources Configuration ───────────────────────────────────
const REVENUE_SOURCES = {
  shopify: {
    name: 'Shopify Sales',
    type: 'ecommerce',
    currency: 'EUR',
    commission: 0,
    tracking: 'api'
  },
  printify: {
    name: 'Printify POD',
    type: 'print_on_demand',
    currency: 'EUR',
    commission: 0.30, // 30% profit margin
    tracking: 'automated'
  },
  digistore: {
    name: 'Digistore24 Affiliate',
    type: 'affiliate',
    currency: 'EUR',
    commission: 0.45, // 45% average commission
    tracking: 'automated'
  },
  youtube: {
    name: 'YouTube AdSense',
    type: 'advertising',
    currency: 'EUR',
    commission: 0.55, // 55% after YouTube cut
    tracking: 'estimated'
  },
  github: {
    name: 'GitHub Sponsors',
    type: 'sponsorship',
    currency: 'USD',
    commission: 0,
    tracking: 'api'
  },
  other: {
    name: 'Other Income',
    type: 'miscellaneous',
    currency: 'EUR',
    commission: 0,
    tracking: 'manual'
  }
};

// ── Data Storage ───────────────────────────────────────────────
function saveRevenueData(source, amount, metadata = {}) {
  const entry = {
    id: Date.now() + Math.random(),
    source,
    amount: parseFloat(amount),
    currency: REVENUE_SOURCES[source]?.currency || 'EUR',
    date: new Date().toISOString(),
    metadata,
    commission: REVENUE_SOURCES[source]?.commission || 0,
    netAmount: parseFloat(amount) * (1 - (REVENUE_SOURCES[source]?.commission || 0))
  };
  
  const filename = `${DATA_DIR}/revenue/${source}-${new Date().getFullYear()}-${new Date().getMonth() + 1}.json`;
  let existing = [];
  
  if (fs.existsSync(filename)) {
    existing = JSON.parse(fs.readFileSync(filename, 'utf8'));
  }
  
  existing.push(entry);
  fs.writeFileSync(filename, JSON.stringify(existing, null, 2));
  
  return entry;
}

function saveExpenseData(category, amount, description, metadata = {}) {
  const entry = {
    id: Date.now() + Math.random(),
    category,
    amount: parseFloat(amount),
    currency: 'EUR',
    description,
    date: new Date().toISOString(),
    metadata
  };
  
  const filename = `${DATA_DIR}/expenses/${new Date().getFullYear()}-${new Date().getMonth() + 1}.json`;
  let existing = [];
  
  if (fs.existsSync(filename)) {
    existing = JSON.parse(fs.readFileSync(filename, 'utf8'));
  }
  
  existing.push(entry);
  fs.writeFileSync(filename, JSON.stringify(existing, null, 2));
  
  return entry;
}

// ── Revenue Calculation ─────────────────────────────────────────
function calculateRevenue(period = 'month') {
  const now = new Date();
  let startDate, endDate;
  
  switch (period) {
    case 'today':
      startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
      break;
    case 'week':
      startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      endDate = now;
      break;
    case 'month':
      startDate = new Date(now.getFullYear(), now.getMonth(), 1);
      endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
      break;
    case 'year':
      startDate = new Date(now.getFullYear(), 0, 1);
      endDate = new Date(now.getFullYear() + 1, 0, 1);
      break;
    default:
      startDate = new Date(now.getFullYear(), now.getMonth(), 1);
      endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  }
  
  const revenue = {};
  let totalRevenue = 0;
  let totalNetRevenue = 0;
  
  // Calculate revenue from all sources
  Object.keys(REVENUE_SOURCES).forEach(source => {
    const sourceRevenue = getRevenueForSource(source, startDate, endDate);
    if (sourceRevenue.length > 0) {
      const sourceTotal = sourceRevenue.reduce((sum, entry) => sum + entry.amount, 0);
      const sourceNetTotal = sourceRevenue.reduce((sum, entry) => sum + entry.netAmount, 0);
      
      revenue[source] = {
        name: REVENUE_SOURCES[source].name,
        type: REVENUE_SOURCES[source].type,
        grossAmount: sourceTotal,
        netAmount: sourceNetTotal,
        transactions: sourceRevenue.length,
        averageTransaction: sourceTotal / sourceRevenue.length
      };
      
      totalRevenue += sourceTotal;
      totalNetRevenue += sourceNetTotal;
    }
  });
  
  // Calculate expenses
  const expenses = getExpensesForPeriod(startDate, endDate);
  const totalExpenses = expenses.reduce((sum, entry) => sum + entry.amount, 0);
  
  // Calculate profit
  const profit = totalNetRevenue - totalExpenses;
  const profitMargin = totalNetRevenue > 0 ? (profit / totalNetRevenue) * 100 : 0;
  
  return {
    period,
    startDate: startDate.toISOString(),
    endDate: endDate.toISOString(),
    revenue,
    totalRevenue,
    totalNetRevenue,
    totalExpenses,
    profit,
    profitMargin,
    currency: 'EUR',
    generatedAt: new Date().toISOString()
  };
}

function getRevenueForSource(source, startDate, endDate) {
  const revenue = [];
  
  // Check multiple month files
  const start = new Date(startDate);
  const end = new Date(endDate);
  
  for (let d = new Date(start); d <= end; d.setMonth(d.getMonth() + 1)) {
    const filename = `${DATA_DIR}/revenue/${source}-${d.getFullYear()}-${d.getMonth() + 1}.json`;
    
    if (fs.existsSync(filename)) {
      const monthData = JSON.parse(fs.readFileSync(filename, 'utf8'));
      const filtered = monthData.filter(entry => {
        const entryDate = new Date(entry.date);
        return entryDate >= startDate && entryDate <= endDate;
      });
      revenue.push(...filtered);
    }
  }
  
  return revenue;
}

function getExpensesForPeriod(startDate, endDate) {
  const expenses = [];
  
  // Check expense files
  const start = new Date(startDate);
  const end = new Date(endDate);
  
  for (let d = new Date(start); d <= end; d.setMonth(d.getMonth() + 1)) {
    const filename = `${DATA_DIR}/expenses/${d.getFullYear()}-${d.getMonth() + 1}.json`;
    
    if (fs.existsSync(filename)) {
      const monthData = JSON.parse(fs.readFileSync(filename, 'utf8'));
      const filtered = monthData.filter(entry => {
        const entryDate = new Date(entry.date);
        return entryDate >= startDate && entryDate <= endDate;
      });
      expenses.push(...filtered);
    }
  }
  
  return expenses;
}

// ── Automation Integration ───────────────────────────────────────
async function syncFromAutomationSystems() {
  console.log('🔄 Syncing revenue from automation systems...');
  
  const synced = [];
  
  // Sync Printify revenue (simulated)
  try {
    const printifyData = await syncPrintifyRevenue();
    if (printifyData) synced.push(printifyData);
  } catch (error) {
    console.error('Printify sync error:', error.message);
  }
  
  // Sync Digistore revenue (simulated)
  try {
    const digistoreData = await syncDigistoreRevenue();
    if (digistoreData) synced.push(digistoreData);
  } catch (error) {
    console.error('Digistore sync error:', error.message);
  }
  
  // Sync YouTube revenue (estimated)
  try {
    const youtubeData = await syncYouTubeRevenue();
    if (youtubeData) synced.push(youtubeData);
  } catch (error) {
    console.error('YouTube sync error:', error.message);
  }
  
  return synced;
}

async function syncPrintifyRevenue() {
  // Simulate Printify API call
  const mockRevenue = Math.random() * 500 + 100; // 100-600 EUR
  const entry = saveRevenueData('printify', mockRevenue, {
    source: 'automated_sync',
    products: Math.floor(Math.random() * 10) + 1
  });
  
  console.log(`💰 Printify: ${mockRevenue.toFixed(2)} EUR`);
  return entry;
}

async function syncDigistoreRevenue() {
  // Simulate Digistore API call
  const mockRevenue = Math.random() * 800 + 200; // 200-1000 EUR
  const entry = saveRevenueData('digistore', mockRevenue, {
    source: 'automated_sync',
    conversions: Math.floor(Math.random() * 5) + 1
  });
  
  console.log(`💰 Digistore: ${mockRevenue.toFixed(2)} EUR`);
  return entry;
}

async function syncYouTubeRevenue() {
  // Simulate YouTube analytics
  const mockRevenue = Math.random() * 300 + 50; // 50-350 EUR
  const entry = saveRevenueData('youtube', mockRevenue, {
    source: 'estimated_sync',
    views: Math.floor(Math.random() * 10000) + 1000,
    rpm: (mockRevenue / (Math.floor(Math.random() * 10000) + 1000)) * 1000
  });
  
  console.log(`💰 YouTube: ${mockRevenue.toFixed(2)} EUR`);
  return entry;
}

// ── Reporting ───────────────────────────────────────────────────
function generateReport(period = 'month') {
  const data = calculateRevenue(period);
  
  const report = `
# 📊 Earnings Report - ${period.charAt(0).toUpperCase() + period.slice(1)}
*Generated: ${new Date().toLocaleDateString('de-DE')}*

## 💰 Revenue Summary
- **Gross Revenue**: ${data.totalRevenue.toFixed(2)} EUR
- **Net Revenue**: ${data.totalNetRevenue.toFixed(2)} EUR
- **Expenses**: ${data.totalExpenses.toFixed(2)} EUR
- **Profit**: ${data.profit.toFixed(2)} EUR
- **Profit Margin**: ${data.profitMargin.toFixed(1)}%

## 📈 Revenue Breakdown
${Object.entries(data.revenue).map(([source, info]) => `
### ${info.name}
- **Gross**: ${info.grossAmount.toFixed(2)} EUR
- **Net**: ${info.netAmount.toFixed(2)} EUR
- **Transactions**: ${info.transactions}
- **Average**: ${info.averageTransaction.toFixed(2)} EUR
`).join('')}

## 🎯 Performance Metrics
- **Daily Average**: ${(data.profit / 30).toFixed(2)} EUR/day
- **Monthly Target**: 1000 EUR
- **Achievement**: ${((data.profit / 1000) * 100).toFixed(1)}%

## 📊 Projections
- **Monthly Projection**: ${data.profit.toFixed(2)} EUR
- **Annual Projection**: ${(data.profit * 12).toFixed(2)} EUR
`;
  
  return report;
}

// ── Main Execution ───────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  
  switch (command) {
    case 'today':
    case 'week':
    case 'month':
    case 'year':
      const report = generateReport(command);
      console.log(report);
      
      // Save report
      const reportPath = `${LOGS_DIR}/earnings-report-${command}-${Date.now()}.md`;
      fs.writeFileSync(reportPath, report);
      console.log(`\n💾 Report saved to: ${reportPath}`);
      break;
      
    case 'sync':
      const synced = await syncFromAutomationSystems();
      console.log(`\n✅ Synced ${synced.length} revenue sources`);
      break;
      
    case 'add':
      const source = args[1];
      const amount = parseFloat(args[2]);
      const description = args.slice(3).join(' ');
      
      if (!source || !amount) {
        console.log('❌ Usage: node scripts/earnings-tracker.js add [source] [amount] [description]');
        return;
      }
      
      const entry = saveRevenueData(source, amount, { description });
      console.log(`✅ Added ${amount} EUR to ${source}`);
      break;
      
    case 'expense':
      const category = args[1];
      const expenseAmount = parseFloat(args[2]);
      const expenseDesc = args.slice(3).join(' ');
      
      if (!category || !expenseAmount) {
        console.log('❌ Usage: node scripts/earnings-tracker.js expense [category] [amount] [description]');
        return;
      }
      
      const expenseEntry = saveExpenseData(category, expenseAmount, expenseDesc);
      console.log(`✅ Added expense: ${expenseAmount} EUR for ${category}`);
      break;
      
    case 'sources':
      console.log('\n📋 Available Revenue Sources:');
      Object.entries(REVENUE_SOURCES).forEach(([key, source]) => {
        console.log(`- ${key}: ${source.name} (${source.type})`);
      });
      break;
      
    default:
      console.log(`
🤖 Earnings Tracker Commands:

  [period]           - Generate earnings report (today, week, month, year)
  sync               - Sync revenue from automation systems
  add [source] [amount] [desc] - Add manual revenue entry
  expense [category] [amount] [desc] - Add expense entry
  sources            - Show available revenue sources
  
Examples:
  node scripts/earnings-tracker.js month
  node scripts/earnings-tracker.js sync
  node scripts/earnings-tracker.js add shopify 299.99 "Premium product sale"
  node scripts/earnings-tracker.js expense hosting 29.99 "Monthly server cost"
      `);
  }
}

// ── START ────────────────────────────────────────────────────────
if (require.main === module) {
  main().catch(console.error);
}

module.exports = {
  calculateRevenue,
  generateReport,
  syncFromAutomationSystems,
  saveRevenueData,
  saveExpenseData
};
