/**
 * RUDIBOT Multi-Agent Collaboration Test
 * Demonstriert wie Agenten zusammenarbeiten
 */

const { AgentCoordinator } = require('./core/agent-coordinator');
const { AgentFactory } = require('./core/agent-templates');

class CollaborationDemo {
  constructor() {
    this.coordinator = new AgentCoordinator({ logger: console });
    this.setupAgents();
  }

  setupAgents() {
    // Shopify Commerce Agent
    const shopify = AgentFactory.createAgent('shopify', {
      id: 'shopify-commerce',
      name: 'Shopify Commerce Agent'
    });

    // Finance Agent
    const finance = AgentFactory.createAgent('finance', {
      id: 'finance-manager',
      name: 'Finance Manager Agent'
    });

    // Support Agent
    const support = AgentFactory.createAgent('support', {
      id: 'support-handler',
      name: 'Customer Support Agent'
    });

    // Analytics Agent
    const analytics = AgentFactory.createAgent('analytics', {
      id: 'analytics-insights',
      name: 'Business Analytics Agent'
    });

    // Revenue Agent
    const revenue = AgentFactory.createAgent('revenue', {
      id: 'revenue-intel',
      name: 'Revenue Intelligence Agent'
    });

    // Register all agents
    [shopify, finance, support, analytics, revenue].forEach(agent => {
      this.coordinator.registerAgent(agent);
    });

    console.log('\n🤖 === AGENTEN REGISTRIERT ===');
    console.log('Alle Agenten sind bereit für die Zusammenarbeit!\n');
  }

  // Demo 1: Order Processing mit Multi-Agent Kollaboration
  async demoOrderProcessing() {
    console.log('📦 === DEMO 1: BESTELLUNG VERARBEITUNG ===');
    console.log('Agenten: Shopify → Finance → Support\n');

    // Schritt 1: Shopify Agent validiert Bestellung
    const task1 = await this.coordinator.createTask({
      type: 'order_validation',
      priority: 'high',
      payload: {
        orderId: '1001',
        customer: 'max@beispiel.de',
        amount: '49.99',
        products: ['T-Shirt Design A']
      },
      requirements: ['shopify_orders_read', 'order_processing'],
      collaboration: {
        requiredCapabilities: ['revenue_tracking'],
        agents: ['finance-manager']
      }
    });

    console.log(`✅ Task erstellt: ${task1.id}`);
    console.log(`🤝 Kollaboration: Shopify + Finance Agent\n`);

    return task1;
  }

  // Demo 2: Revenue Analysis mit Analytics + Revenue Agent
  async demoRevenueAnalysis() {
    console.log('📊 === DEMO 2: UMSATZ ANALYSE ===');
    console.log('Agenten: Analytics → Revenue → Support\n');

    const task = await this.coordinator.createTask({
      type: 'revenue_analysis',
      priority: 'medium',
      payload: {
        period: 'last_30_days',
        includeForecast: true
      },
      requirements: ['data_analysis', 'revenue_forecasting'],
      collaboration: {
        requiredCapabilities: ['trend_identification', 'revenue_forecasting'],
        agents: ['analytics-insights', 'revenue-intel']
      }
    });

    console.log(`✅ Task erstellt: ${task.id}`);
    console.log(`🤝 Kollaboration: Analytics + Revenue Agent\n`);

    return task;
  }

  // Demo 3: Customer Support mit WISMO + Shopify
  async demoCustomerSupport() {
    console.log('💬 === DEMO 3: KUNDEN SUPPORT ===');
    console.log('Agenten: Support → Shopify → Analytics\n');

    const task = await this.coordinator.createTask({
      type: 'customer_inquiry',
      priority: 'high',
      payload: {
        inquiryType: 'wismo',
        customerEmail: 'kunde@beispiel.de',
        orderNumber: '1001',
        message: 'Wo ist meine Bestellung?'
      },
      requirements: ['ticket_management', 'order_tracking'],
      collaboration: {
        requiredCapabilities: ['shopify_orders_read', 'customer_communication'],
        agents: ['shopify-commerce', 'support-handler']
      }
    });

    console.log(`✅ Task erstellt: ${task.id}`);
    console.log(`🤝 Kollaboration: Support + Shopify Agent\n`);

    return task;
  }

  // Demo 4: Agent Communication
  async demoAgentCommunication() {
    console.log('📡 === DEMO 4: AGENTEN KOMMUNIKATION ===\n');

    // Nachricht von Coordinator an Shopify Agent
    const msg1 = await this.coordinator.sendMessage('shopify-commerce', {
      type: 'order_notification',
      content: 'Neue Bestellung #1001 eingegangen',
      priority: 'high'
    });

    console.log(`📨 Nachricht an Shopify Agent: ${msg1.type}`);

    // Nachricht von Coordinator an Finance Agent
    const msg2 = await this.coordinator.sendMessage('finance-manager', {
      type: 'revenue_alert',
      content: 'Umsatz über 1000 EUR erreicht',
      amount: '1000.00'
    });

    console.log(`📨 Nachricht an Finance Agent: ${msg2.type}`);

    // Broadcast an alle Commerce Agenten
    const broadcast = await this.coordinator.broadcastMessage('commerce', {
      type: 'system_update',
      content: 'Neue Produkte verfügbar'
    });

    console.log(`📢 Broadcast an Commerce Gruppe: ${broadcast.type}\n`);
  }

  // Demo 5: Resource Locking (Konfliktlösung)
  async demoResourceLocking() {
    console.log('🔒 === DEMO 5: RESSOURCEN VERWALTUNG ===\n');

    // Shopify Agent sperrt Shopify API
    const lock1 = await this.coordinator.acquireResource('shopify-api', 'shopify-commerce', 30000);
    console.log(`🔐 Shopify API gesperrt von Shopify Agent: ${lock1.success ? 'Erfolg' : 'Fehler'}`);

    // Finance Agent versucht gleiche API zu sperren
    const lock2 = await this.coordinator.acquireResource('shopify-api', 'finance-manager', 30000);
    console.log(`🔐 Shopify API gesperrt von Finance Agent: ${lock2.success ? 'Erfolg' : 'Fehler'}`);

    if (!lock2.success) {
      console.log(`⚠️  Konflikt erkannt! Finance Agent muss warten.`);
    }

    // Shopify Agent gibt Ressource frei
    const release = await this.coordinator.releaseResource('shopify-api', 'shopify-commerce');
    console.log(`🔓 Shopify API freigegeben: ${release.success ? 'Erfolg' : 'Fehler'}`);

    // Finance Agent kann jetzt sperren
    const lock3 = await this.coordinator.acquireResource('shopify-api', 'finance-manager', 30000);
    console.log(`🔐 Shopify API gesperrt von Finance Agent: ${lock3.success ? 'Erfolg' : 'Fehler'}`);
  }

  // Status Report
  async printStatus() {
    const status = this.coordinator.getCoordinatorStatus();

    console.log('\n📊 === SYSTEM STATUS ===');
    console.log(`Agenten: ${status.agents.length}`);
    console.log(`Aufgaben: ${status.tasks.pending} pending, ${status.tasks.active} active`);
    console.log(`Kollaborationen: ${status.collaborations.active} active`);
    console.log(`Ressourcen: ${status.resources.locked} locked\n`);

    console.log('🤖 Agenten Status:');
    status.agents.forEach(agent => {
      const statusIcon = agent.status === 'idle' ? '🟢' : agent.status === 'busy' ? '🔵' : '🔴';
      console.log(`  ${statusIcon} ${agent.name} (${agent.type}) - ${agent.status}`);
      console.log(`     Aufgaben: ${agent.currentTasks} | Erfolg: ${(agent.successRate * 100).toFixed(0)}%`);
    });
  }

  // Run all demos
  async runAllDemos() {
    console.log('\n');
    console.log('╔════════════════════════════════════════════════════════════╗');
    console.log('║     RUDIBOT MULTI-AGENT KOLLABORATION DEMO              ║');
    console.log('╚════════════════════════════════════════════════════════════╝\n');

    await this.printStatus();

    await this.demoOrderProcessing();
    await this.demoRevenueAnalysis();
    await this.demoCustomerSupport();
    await this.demoAgentCommunication();
    await this.demoResourceLocking();

    console.log('\n✅ === ALLE DEMOS ABGESCHLOSSEN ===\n');
    await this.printStatus();

    console.log('\n🎯 Nächste Schritte:');
    console.log('   1. Shopify Token erneuern');
    console.log('   2. Echte API Keys eintragen');
    console.log('   3. Workflows mit echten Daten testen');
    console.log('   4. Produktions-Deployment vorbereiten\n');
  }
}

// Run if called directly
if (require.main === module) {
  const demo = new CollaborationDemo();
  demo.runAllDemos().catch(console.error);
}

module.exports = { CollaborationDemo };
