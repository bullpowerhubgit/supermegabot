/**
 * 🚀 Quick Start Example für andere Agenten
 * Kopiere dieses Skript um sofort mit Revenue First Mode zu starten
 */

const fetch = require('node-fetch');

// Konfiguration - passe an deine Umgebung an
const RUDIBOT_URL = 'http://localhost:3200';

class RevenueFirstAgent {
  constructor(baseUrl = RUDIBOT_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * 🎯 Quick Revenue Check - sollte vor jeder Aktion ausgeführt werden
   */
  async shouldProceedWithAction(actionCost = 0) {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/should-proceed?cost=${actionCost}`);
      const data = await response.json();
      
      if (data.success) {
        console.log(`💰 Revenue: €${data.data.revenue}`);
        console.log(`💸 Costs: €${data.data.costs}`);
        console.log(`📊 Net Profit: €${data.data.netProfit}`);
        console.log(`🎯 Recommendation: ${data.data.recommendation}`);
        
        return data.data;
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error('❌ Revenue Check failed:', error.message);
      return { canProceed: false, error: error.message };
    }
  }

  /**
   * 📈 Aktuelle Umsatz-Statistiken holen
   */
  async getRevenueOverview() {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/revenue-overview`);
      const data = await response.json();
      
      if (data.success) {
        console.log(`📊 Today's Revenue: €${data.data.revenue.today}`);
        console.log(`📊 Total Revenue: €${data.data.revenue.total}`);
        console.log(`📦 Active Orders: ${data.data.revenue.pendingOrders}`);
        console.log(`💸 Total Costs: €${data.data.costs.total}`);
        console.log(`📈 Net Profit: €${data.data.netProfit}`);
        console.log(`🟢 Status: ${data.data.status}`);
        
        return data.data;
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error('❌ Revenue Overview failed:', error.message);
      return null;
    }
  }

  /**
   * 💡 Kosten-Saving-Opportunities finden
   */
  async findCostSavings(minSavings = 10) {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/cost-savings?minSavings=${minSavings}`);
      const data = await response.json();
      
      if (data.success) {
        console.log(`💰 Potential Savings: €${data.data.totalSavings}`);
        console.log(`🎯 Opportunities: ${data.data.count}`);
        
        data.data.opportunities.forEach((opp, i) => {
          console.log(`${i + 1}. ${opp.name}: €${opp.savingAmount} (${opp.priority})`);
        });
        
        return data.data.opportunities;
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error('❌ Cost Savings analysis failed:', error.message);
      return [];
    }
  }

  /**
   * 🔧 Job ausführen (z.B. Daten synchronisieren)
   */
  async executeJob(jobName, params = {}) {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/execute-job`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobName, params })
      });
      
      const data = await response.json();
      
      if (data.success) {
        console.log(`✅ Job '${jobName}' executed successfully`);
        console.log(`📋 Type: ${data.data.type}`);
        console.log(`📊 Result:`, data.data.result);
        
        return data.data.result;
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error(`❌ Job '${jobName}' failed:`, error.message);
      return null;
    }
  }

  /**
   * 📦 Shopify-Order-Status prüfen
   */
  async getOrderStatus(orderId) {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/order-status/${orderId}`);
      const data = await response.json();
      
      if (data.success) {
        console.log(`📦 Order ${data.data.orderId}:`);
        console.log(`   💰 Revenue: €${data.data.revenue}`);
        console.log(`   💳 Status: ${data.data.status}`);
        console.log(`   🚚 Fulfillment: ${data.data.fulfillmentStatus}`);
        console.log(`   ✅ Paid: ${data.data.isPaid}`);
        
        return data.data;
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error(`❌ Order ${orderId} check failed:`, error.message);
      return null;
    }
  }

  /**
   * 🏥 System-Health prüfen
   */
  async getHealthStatus() {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/health-check`);
      const data = await response.json();
      
      if (data.success) {
        console.log(`🏥 System Health:`);
        console.log(`   📊 Revenue First Mode: ${data.data.revenueFirstMode.status}`);
        console.log(`   🛒 Shopify API: ${data.data.apis.shopify ? '✅' : '❌'}`);
        console.log(`   💳 PayPal API: ${data.data.apis.paypal ? '✅' : '❌'}`);
        console.log(`   🎨 Printify API: ${data.data.apis.printify ? '✅' : '❌'}`);
        console.log(`   📈 Overall: ${data.data.overall}`);
        
        return data.data;
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error('❌ Health check failed:', error.message);
      return null;
    }
  }

  /**
   * 📡 Nachricht an andere Agenten senden
   */
  async broadcastMessage(type, data, priority = 'medium') {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/broadcast`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, data, priority })
      });
      
      const result = await response.json();
      
      if (result.success) {
        console.log(`📡 Message broadcasted: ${type}`);
        return result.data;
      } else {
        throw new Error(result.error);
      }
    } catch (error) {
      console.error('❌ Broadcast failed:', error.message);
      return null;
    }
  }

  /**
   * ⚡ Super-schnelle Statistiken für Dashboards
   */
  async getQuickStats() {
    try {
      const response = await fetch(`${this.baseUrl}/api/agent-help/quick-stats`);
      const data = await response.json();
      
      if (data.success) {
        return data.data;
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error('❌ Quick stats failed:', error.message);
      return null;
    }
  }
}

// 🚀 Beispiel-Nutzung
async function exampleUsage() {
  const agent = new RevenueFirstAgent();

  console.log('🎯 Revenue First Agent - Quick Start Example\n');

  // 1. System-Health prüfen
  console.log('1️⃣ Checking system health...');
  await agent.getHealthStatus();
  console.log('');

  // 2. Revenue-Check vor Aktion
  console.log('2️⃣ Checking if we should proceed with action...');
  const shouldProceed = await agent.shouldProceedWithAction(50); // 50€ Kosten
  console.log('');

  // 3. Revenue-Overview
  console.log('3️⃣ Getting revenue overview...');
  await agent.getRevenueOverview();
  console.log('');

  // 4. Kosten-Savings finden
  console.log('4️⃣ Finding cost saving opportunities...');
  await agent.findCostSavings(20); // Mindest 20€ Einsparung
  console.log('');

  // 5. Job ausführen (Daten sync)
  console.log('5️⃣ Executing sync job...');
  await agent.executeJob('sync-shopify-orders');
  console.log('');

  // 6. Quick Stats für Dashboard
  console.log('6️⃣ Getting quick stats...');
  const stats = await agent.getQuickStats();
  if (stats) {
    console.log(`📊 Dashboard Stats: ${stats.status} Revenue: €${stats.revenue} | Costs: €${stats.costs} | Profit: €${stats.profit}`);
  }
  console.log('');

  // 7. Nachricht broadcasten
  console.log('7️⃣ Broadcasting message to other agents...');
  await agent.broadcastMessage('revenue_update', {
    newOrder: true,
    amount: 149.99,
    impact: 'positive'
  }, 'high');
  console.log('');

  console.log('✅ Example completed! Your agent is now Revenue First ready. 🚀');
}

// Export für Nutzung in anderen Skripten
module.exports = { RevenueFirstAgent, exampleUsage };

// Wenn direkt ausgeführt, starte das Beispiel
if (require.main === module) {
  exampleUsage().catch(console.error);
}
