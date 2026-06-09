# Revenue First Mode - Agent Integration Guide

## 🎯 Quick Start für andere Agenten

Dein Agent kann sofort mit Revenue First Mode starten - keine komplexen Setup-Schritte nötig.

### 1. Basis-Integration (5 Minuten)

```javascript
// Importiere den Revenue First Mode
const { RevenueFirstMode } = require('./core/revenue-first');
const { AppContext } = require('./core/app-context');

// Initialisiere mit existierender Konfiguration
const context = new AppContext();
const revenueMode = new RevenueFirstMode(context);

// Hole sofort Umsatz-Daten
async function getRevenueOverview() {
  const dashboard = await revenueMode.generateRevenueDashboard();
  return {
    totalRevenue: dashboard.revenue.total,
    todayRevenue: dashboard.revenue.today,
    activeOrders: dashboard.revenue.pendingOrders,
    costs: dashboard.costs.total,
    netProfit: dashboard.revenue.total - dashboard.costs.total
  };
}
```

### 2. API-Endpunkte für externe Agenten

```
GET  /api/revenue-first/overview     # Komplettes Dashboard
GET  /api/revenue-first/revenue       # Nur Umsatz-Daten
GET  /api/revenue-first/costs         # Nur Kosten-Daten
GET  /api/revenue-first/actions       # Sofort umsetzbare Aktionen
POST /api/revenue-first/trigger-job   # Job ausführen
```

### 3. Fertige Patterns für häufige Use-Cases

#### A) Umsatz-Check vor jeder Aktion
```javascript
async function shouldProceedWithAction(actionCost = 0) {
  const revenue = await revenueMode.getRevenueToday();
  const costs = await revenueMode.getCostsToday();
  const netProfit = revenue - costs - actionCost;
  
  return {
    canProceed: netProfit > 0,
    revenue: revenue,
    costs: costs,
    recommendation: netProfit > 0 ? "GO" : "WAIT"
  };
}
```

#### B) Kosten-Scan für Optimierung
```javascript
async function findCostSavings() {
  const costAnalysis = await revenueMode.identifyCostSavingOpportunities();
  return costAnalysis.potentialSavings.filter(saving => 
    saving.priority === 'high' && saving.savingAmount > 10
  );
}
```

#### C) Shopify-Order-Status
```javascript
async function getOrderStatus(orderId) {
  const order = await context.shopify.getOrder(orderId);
  const revenue = await revenueMode.calculateOrderRevenue(order);
  
  return {
    orderId: order.id,
    status: order.financial_status,
    revenue: revenue,
    isPaid: order.financial_status === 'paid',
    actions: revenueMode.getOrderActions(order)
  };
}
```

## 🔧 Konfiguration für andere Agenten

### Environment-Variablen (minimal)
```bash
# Nur diese 3 sind kritisch für den Start
SHOPIFY_STORE_URL=dein-store.myshopify.com
SHOPIFY_ADMIN_TOKEN=shpat_...
NODE_ENV=production
```

### Optionale Erweiterungen
```bash
# Für volle Features
PAYPAL_CLIENT_ID=...
KLAVIYO_API_KEY=...
TELEGRAM_BOT_TOKEN=...
```

## 📊 Dashboard-Integration

### Embeddable Dashboard
```html
<!-- Füge dieses Widget in jeden Agent ein -->
<iframe 
  src="http://localhost:3000/revenue-first" 
  width="100%" 
  height="600"
  frameborder="0">
</iframe>
```

### API-Beispiel: Live-Daten holen
```javascript
const response = await fetch('http://localhost:3000/api/revenue-first/overview');
const data = await response.json();

console.log(`Heutiger Umsatz: €${data.revenue.today}`);
console.log(`Aktive Kosten: €${data.costs.total}`);
console.log(`Netto-Gewinn: €${data.revenue.total - data.costs.total}`);
```

## 🚀 Job-System für Agenten

### Vordefinierte Jobs (direkt nutzbar)
```javascript
// Umsatz synchronisieren
await revenueMode.executeJob('sync-shopify-orders');

// Kosten scannen
await revenueMode.executeJob('scan-subscriptions');

// Kündigungs-Kandidaten finden
await revenueMode.executeJob('identify-cancellation-candidates');
```

### Custom Jobs für deinen Agenten
```javascript
// Eigener Job mit Revenue-Check
const customJob = {
  name: 'agent-specific-action',
  category: 'REVENUE',
  priority: 'high',
  execute: async () => {
    const revenue = await revenueMode.getRevenueToday();
    if (revenue > 100) {
      console.log('✅ Genug Umsatz für Aktion');
      return await performAgentAction();
    } else {
      console.log('⚠️  Zu wenig Umsatz - warte');
      return { status: 'deferred', reason: 'insufficient_revenue' };
    }
  }
};

await revenueMode.executeCustomJob(customJob);
```

## 🛡️ Sicherheits-Features

### Auto-Approval für sichere Aktionen
```javascript
const safeJobs = [
  'sync-shopify-orders',
  'calculate-revenue',
  'scan-costs',
  'generate-report'
];

// Diese Jobs laufen automatisch ohne Genehmigung
for (const job of safeJobs) {
  await revenueMode.executeJob(job);
}
```

### Approval-Required für kritische Aktionen
```javascript
const criticalJobs = [
  'cancel-subscription',
  'process-refund',
  'delete-customer-data'
];

// Diese brauchen manuelle Bestätigung
const result = await revenueMode.executeJob('cancel-subscription', {
  requiresApproval: true,
  reason: 'Kostenreduktion: unused service'
});
```

## 📈 Monitoring & Health-Checks

### System-Status prüfen
```javascript
const health = await revenueMode.getSystemHealth();
console.log(`
📊 Revenue First Mode Status:
- Umsatz-Tracking: ${health.revenueTracking ? '✅' : '❌'}
- Kosten-Tracking: ${health.costTracking ? '✅' : '❌'}
- Shopify-API: ${health.shopifyApi ? '✅' : '❌'}
- Job-Queue: ${health.jobQueue ? '✅' : '❌'}
`);
```

### Live-Connection Test
```bash
# Führe diesen Test aus bevor du startest
node scripts/test-live-connections.js
```

## 🤝 Multi-Agent-Kommunikation

### Agent-zu-Agent Nachrichten
```javascript
// Sende Nachricht an andere Agenten
await revenueMode.broadcastToAgents({
  type: 'revenue_update',
  data: {
    newOrder: true,
    amount: 149.99,
    impact: 'positive'
  },
  priority: 'high'
});

// Empfange Nachrichten von anderen Agenten
revenueMode.onAgentMessage((message) => {
  if (message.type === 'cost_alert') {
    console.log(`⚠️  Kosten-Alarm: ${message.data.amount}`);
  }
});
```

## 🎯 Best Practices

### 1. Immer Revenue-Check vor Aktionen
```javascript
const revenue = await revenueMode.getRevenueToday();
if (revenue < 50) {
  console.log('⚠️  Niedriger Umsatz - kritische Aktionen pausieren');
  return;
}
```

### 2. Kosten vor jeder Ausgabe prüfen
```javascript
const costs = await revenueMode.getCostsToday();
const budget = await revenueMode.getAvailableBudget();
if (costs > budget * 0.8) {
  console.log('⚠️  Budget-Limit erreicht - neue Ausgaben blockieren');
  return;
}
```

### 3. Fehlerbehandlung mit Fallback
```javascript
try {
  const result = await revenueMode.executeJob('sync-shopify-orders');
  console.log('✅ Sync erfolgreich');
} catch (error) {
  console.log('❌ Sync fehlgeschlagen - nutze Cache');
  const cached = await revenueMode.getCachedRevenue();
  return cached;
}
```

## 📞 Support & Hilfe

### Live-Hilfe erhalten
```javascript
// Rufe den Support-Agenten
await revenueMode.callSupportAgent({
  issue: 'shopify-api-error',
  urgency: 'high',
  context: { orderId: 12345 }
});
```

### Debug-Modus aktivieren
```javascript
process.env.DEBUG_REVENUE_FIRST = 'true';
// Jetzt siehst du alle API-Calls und Entscheidungen
```

---

## 🚀 Sofort loslegen

1. **Kopiere** die Quick-Start Code-Snippets
2. **Setze** die 3 Environment-Variablen
3. **Starte** den Server: `npm start`
4. **Teste** mit: `node scripts/test-live-connections.js`
5. **Integriere** deine Agent-Logik

Fertig! Dein Agent ist jetzt Revenue-First-optimiert. 🎯
