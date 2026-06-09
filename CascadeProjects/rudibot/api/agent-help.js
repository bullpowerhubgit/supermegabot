/**
 * API-Endpunkt für andere Agenten zur Nutzung von Revenue First Mode
 * Stellt einfache REST-Schnittstelle für Multi-Agent-Integration bereit
 */

const express = require('express');
const { RevenueFirstMode } = require('../core/revenue-first');
const { AppContext } = require('../core/app-context');

const router = express.Router();

// Initialisiere Revenue First Mode für Agent-Hilfe
let revenueMode = null;
let context = null;

async function initializeRevenueMode() {
  if (!revenueMode) {
    context = new AppContext();
    // RevenueFirstMode braucht auch einen Orchestrator
    const { Orchestrator } = require('../core/orchestrator');
    const orchestrator = new Orchestrator();
    revenueMode = new RevenueFirstMode(context, orchestrator);
  }
}

/**
 * GET /api/agent-help/revenue-overview
 * Schneller Umsatz-Check für andere Agenten
 */
router.get('/revenue-overview', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const dashboard = await revenueMode.generateRevenueDashboard();
    
    res.json({
      success: true,
      data: {
        revenue: {
          today: dashboard.revenue.today,
          total: dashboard.revenue.total,
          pendingOrders: dashboard.revenue.pendingOrders,
          todayOrders: dashboard.revenue.todayOrders
        },
        costs: {
          total: dashboard.costs.total,
          subscriptions: dashboard.costs.subscriptions,
          transactions: dashboard.costs.transactions
        },
        netProfit: dashboard.revenue.total - dashboard.costs.total,
        status: dashboard.revenue.total > dashboard.costs.total ? 'HEALTHY' : 'WARNING',
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /api/agent-help/should-proceed
 * Prüft ob Agent eine Aktion ausführen sollte (Revenue-Check)
 */
router.get('/should-proceed', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const actionCost = parseFloat(req.query.cost) || 0;
    const revenue = await revenueMode.getRevenueToday();
    const costs = await revenueMode.getCostsToday();
    const netProfit = revenue - costs - actionCost;
    
    res.json({
      success: true,
      data: {
        canProceed: netProfit > 0,
        revenue: revenue,
        costs: costs,
        actionCost: actionCost,
        netProfit: netProfit,
        recommendation: netProfit > 0 ? 'GO' : 'WAIT',
        reason: netProfit > 0 ? 'Sufficient revenue' : 'Insufficient revenue',
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /api/agent-help/cost-savings
 * Findet Kosten-Saving-Opportunities für andere Agenten
 */
router.get('/cost-savings', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const costAnalysis = await revenueMode.identifyCostSavingOpportunities();
    const minSavings = parseFloat(req.query.minSavings) || 10;
    
    const filteredSavings = costAnalysis.potentialSavings.filter(saving => 
      saving.savingAmount >= minSavings && 
      (saving.priority === 'high' || saving.priority === 'medium')
    );
    
    res.json({
      success: true,
      data: {
        totalSavings: filteredSavings.reduce((sum, s) => sum + s.savingAmount, 0),
        opportunities: filteredSavings,
        count: filteredSavings.length,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * POST /api/agent-help/execute-job
 * Führt einen Revenue-First Job für andere Agenten aus
 */
router.post('/execute-job', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const { jobName, params = {} } = req.body;
    
    if (!jobName) {
      return res.status(400).json({
        success: false,
        error: 'jobName is required',
        timestamp: new Date().toISOString()
      });
    }
    
    // Safe Jobs - können automatisch ausgeführt werden
    const safeJobs = [
      'sync-shopify-orders',
      'sync-shopify-products',
      'calculate-revenue',
      'scan-costs',
      'generate-report',
      'check-payment-status'
    ];
    
    // Critical Jobs - brauchen Approval
    const criticalJobs = [
      'cancel-subscription',
      'process-refund',
      'delete-customer-data'
    ];
    
    let result;
    
    if (safeJobs.includes(jobName)) {
      result = await revenueMode.executeJob(jobName, params);
    } else if (criticalJobs.includes(jobName)) {
      result = await revenueMode.executeJob(jobName, {
        ...params,
        requiresApproval: true,
        reason: params.reason || 'Requested by external agent'
      });
    } else {
      // Custom Job
      result = await revenueMode.executeCustomJob({
        name: jobName,
        category: params.category || 'REVENUE',
        priority: params.priority || 'medium',
        execute: params.execute,
        ...params
      });
    }
    
    res.json({
      success: true,
      data: {
        jobName: jobName,
        result: result,
        type: safeJobs.includes(jobName) ? 'AUTO' : 'APPROVAL_REQUIRED',
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /api/agent-help/order-status/:orderId
 * Shopify-Order-Status für andere Agenten
 */
router.get('/order-status/:orderId', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const orderId = req.params.orderId;
    const order = await context.shopify.getOrder(orderId);
    const revenue = await revenueMode.calculateOrderRevenue(order);
    const actions = revenueMode.getOrderActions(order);
    
    res.json({
      success: true,
      data: {
        orderId: order.id,
        status: order.financial_status,
        fulfillmentStatus: order.fulfillment_status,
        revenue: revenue,
        isPaid: order.financial_status === 'paid',
        isFulfilled: order.fulfillment_status === 'fulfilled',
        actions: actions,
        customerEmail: order.email,
        totalPrice: order.total_price,
        currency: order.currency,
        createdAt: order.created_at,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /api/agent-help/health-check
 * System-Health für andere Agenten
 */
router.get('/health-check', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const health = await revenueMode.getSystemHealth();
    
    res.json({
      success: true,
      data: {
        revenueFirstMode: {
          active: health.revenueTracking || false,
          status: health.revenueTracking ? 'HEALTHY' : 'ERROR'
        },
        apis: {
          shopify: health.shopifyApi || false,
          paypal: health.paypalApi || false,
          printify: health.printifyApi || false
        },
        systems: {
          jobQueue: health.jobQueue || false,
          costTracking: health.costTracking || false,
          scheduler: health.scheduler || false
        },
        overall: health.revenueTracking && health.shopifyApi ? 'HEALTHY' : 'WARNING',
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * POST /api/agent-help/broadcast
 * Nachricht an andere Agenten senden
 */
router.post('/broadcast', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const { type, data, priority = 'medium' } = req.body;
    
    if (!type || !data) {
      return res.status(400).json({
        success: false,
        error: 'type and data are required',
        timestamp: new Date().toISOString()
      });
    }
    
    // Simuliere Broadcast an andere Agenten
    const broadcastResult = await revenueMode.broadcastToAgents({
      type,
      data,
      priority,
      from: 'external-agent',
      timestamp: new Date().toISOString()
    });
    
    res.json({
      success: true,
      data: {
        broadcast: broadcastResult,
        message: 'Message broadcasted to agents',
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /api/agent-help/quick-stats
 * Super-schnelle Statistiken für Agent-Dashboards
 */
router.get('/quick-stats', async (req, res) => {
  try {
    await initializeRevenueMode();
    
    const dashboard = await revenueMode.generateRevenueDashboard();
    
    res.json({
      success: true,
      data: {
        revenue: dashboard.revenue.today,
        costs: dashboard.costs.total,
        orders: dashboard.revenue.todayOrders,
        profit: dashboard.revenue.total - dashboard.costs.total,
        status: dashboard.revenue.total > dashboard.costs.total ? '🟢' : '🟡',
        trend: dashboard.revenue.trend || 'stable',
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
