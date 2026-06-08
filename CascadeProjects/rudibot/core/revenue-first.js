/**
 * Revenue First Mode Controller
 * Priorisiert Umsatz, Kostenkontrolle und produktive Aktionen
 */

class RevenueFirstMode {
  constructor(context, orchestrator) {
    this.context = context;
    this.orchestrator = orchestrator;
    this.logger = console;
    
    // Revenue First Kategorien
    this.categories = {
      REVENUE_GENERATING: 'bringt Geld rein',
      COST_SAVING: 'spart Geld', 
      REVENUE_PROTECTING: 'schützt Umsatz',
      OPERATIONAL_CRITICAL: 'schützt Betrieb'
    };
    
    // Prioritäten-Matrix
    this.priorities = {
      HIGHEST: ['shopify', 'revenue', 'orders', 'payments'],
      HIGH: ['cost_tracking', 'subscriptions', 'cancellations'],
      MEDIUM: ['support_automation', 'problem_resolution'],
      LOW: ['comfort_features', 'demos', 'mockups']
    };
    
    this.initializeRevenueTracking();
  }

  initializeRevenueTracking() {
    // Revenue-Metriken initialisieren
    this.metrics = {
      daily: {
        revenue: 0,
        orders: 0,
        costs: 0,
        profit: 0
      },
      weekly: {
        revenue: 0,
        orders: 0,
        costs: 0,
        profit: 0
      },
      monthly: {
        revenue: 0,
        orders: 0,
        costs: 0,
        profit: 0
      }
    };

    this.logger.info('💰 Revenue First Mode aktiviert');
  }

  // Prüft ob Task Revenue-First-konform ist
  isRevenueFirst(task) {
    const category = this.categorizeTask(task);
    const priority = this.getPriority(task);
    
    return {
      approved: category !== null && priority !== 'LOW',
      category,
      priority,
      reason: this.getApprovalReason(category, priority)
    };
  }

  categorizeTask(task) {
    const keywords = task.toLowerCase();
    
    // Umsatz-generierende Tasks
    if (keywords.includes('shopify') || keywords.includes('order') || 
        keywords.includes('revenue') || keywords.includes('payment') ||
        keywords.includes('verkauf') || keywords.includes('umsatz')) {
      return this.categories.REVENUE_GENERATING;
    }
    
    // Kosten-sparende Tasks
    if (keywords.includes('cost') || keywords.includes('kosten') ||
        keywords.includes('subscription') || keywords.includes('cancel') ||
        keywords.includes('kündigung') || keywords.includes('sparen')) {
      return this.categories.COST_SAVING;
    }
    
    // Umsatz-schützende Tasks
    if (keywords.includes('security') || keywords.includes('backup') ||
        keywords.includes('monitoring') || keywords.includes('health') ||
        keywords.includes('stabilität') || keywords.includes('betrieb')) {
      return this.categories.REVENUE_PROTECTING;
    }
    
    // Betriebskritische Tasks
    if (keywords.includes('hosting') || keywords.includes('domain') ||
        keywords.includes('api') || keywords.includes('core') ||
        keywords.includes('steuer') || keywords.includes('elster')) {
      return this.categories.OPERATIONAL_CRITICAL;
    }
    
    return null; // Nicht Revenue-First
  }

  getPriority(task) {
    const keywords = task.toLowerCase();
    
    for (const [priority, priorityKeywords] of Object.entries(this.priorities)) {
      for (const keyword of priorityKeywords) {
        if (keywords.includes(keyword)) {
          return priority;
        }
      }
    }
    
    return 'LOW';
  }

  getApprovalReason(category, priority) {
    if (priority === 'HIGHEST') {
      return `Höchste Priorität: ${category}`;
    }
    if (priority === 'HIGH') {
      return `Hohe Priorität: ${category}`;
    }
    if (priority === 'MEDIUM') {
      return `Mittlere Priorität: ${category}`;
    }
    return 'Keine Revenue-First Priorität';
  }

  // Revenue Dashboard mit echten Daten
  async getRevenueDashboard() {
    try {
      const shopify = this.context.getService('shopify');
      const finance = this.context.getService('paypal');
      
      // Echte Shopify-Daten holen
      const todayRevenue = await this.getTodayRevenue();
      const weeklyRevenue = await this.getWeeklyRevenue();
      const monthlyRevenue = await this.getMonthlyRevenue();
      
      // Echte Kosten-Daten
      const todayCosts = await this.getTodayCosts();
      const weeklyCosts = await this.getWeeklyCosts();
      const monthlyCosts = await this.getMonthlyCosts();
      
      return {
        timestamp: new Date(),
        revenue: {
          today: todayRevenue,
          weekly: weeklyRevenue,
          monthly: monthlyRevenue
        },
        costs: {
          today: todayCosts,
          weekly: weeklyCosts,
          monthly: monthlyCosts
        },
        profit: {
          today: todayRevenue - todayCosts,
          weekly: weeklyRevenue - weeklyCosts,
          monthly: monthlyRevenue - monthlyCosts
        },
        metrics: {
          ordersToday: await this.getOrdersCount('today'),
          ordersWeek: await this.getOrdersCount('week'),
          ordersMonth: await this.getOrdersCount('month'),
          avgOrderValue: await this.getAverageOrderValue(),
          conversionRate: await this.getConversionRate()
        }
      };
    } catch (error) {
      this.logger.error('Revenue Dashboard Fehler:', error);
      return this.getFallbackDashboard();
    }
  }

  // Echte Shopify Revenue-Daten
  async getTodayRevenue() {
    try {
      const shopify = this.context.getService('shopify');
      const today = new Date().toISOString().split('T')[0];
      
      const orders = await shopify.getOrders({
        created_at_min: today,
        status: 'any'
      });
      
      return orders.orders?.reduce((sum, order) => sum + parseFloat(order.total_price), 0) || 0;
    } catch (error) {
      this.logger.error('Today Revenue Fehler:', error);
      return 0;
    }
  }

  async getWeeklyRevenue() {
    try {
      const shopify = this.context.getService('shopify');
      const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
      
      const orders = await shopify.getOrders({
        created_at_min: weekAgo,
        status: 'any'
      });
      
      return orders.orders?.reduce((sum, order) => sum + parseFloat(order.total_price), 0) || 0;
    } catch (error) {
      this.logger.error('Weekly Revenue Fehler:', error);
      return 0;
    }
  }

  async getMonthlyRevenue() {
    try {
      const shopify = this.context.getService('shopify');
      const monthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
      
      const orders = await shopify.getOrders({
        created_at_min: monthAgo,
        status: 'any'
      });
      
      return orders.orders?.reduce((sum, order) => sum + parseFloat(order.total_price), 0) || 0;
    } catch (error) {
      this.logger.error('Monthly Revenue Fehler:', error);
      return 0;
    }
  }

  // Echte Kosten-Daten
  async getTodayCosts() {
    try {
      const costs = await this.getActiveSubscriptions();
      const dailyCosts = costs.reduce((sum, sub) => sum + (sub.monthlyCost / 30), 0);
      return dailyCosts;
    } catch (error) {
      this.logger.error('Today Costs Fehler:', error);
      return 0;
    }
  }

  async getWeeklyCosts() {
    try {
      const costs = await this.getActiveSubscriptions();
      const weeklyCosts = costs.reduce((sum, sub) => sum + (sub.monthlyCost / 4.3), 0);
      return weeklyCosts;
    } catch (error) {
      this.logger.error('Weekly Costs Fehler:', error);
      return 0;
    }
  }

  async getMonthlyCosts() {
    try {
      const costs = await this.getActiveSubscriptions();
      const monthlyCosts = costs.reduce((sum, sub) => sum + sub.monthlyCost, 0);
      return monthlyCosts;
    } catch (error) {
      this.logger.error('Monthly Costs Fehler:', error);
      return 0;
    }
  }

  // Aktive Subscriptions aus echten Daten
  async getActiveSubscriptions() {
    try {
      // PayPal Subscriptions
      const paypal = this.context.getService('paypal');
      const subscriptions = await paypal.getSubscriptions();
      
      return subscriptions.map(sub => ({
        name: sub.description || 'Unknown',
        provider: 'PayPal',
        monthlyCost: parseFloat(sub.amount.total),
        status: sub.status,
        nextBilling: sub.next_billing_time
      }));
    } catch (error) {
      this.logger.error('Subscriptions Fehler:', error);
      return [];
    }
  }

  // Order Metriken
  async getOrdersCount(period) {
    try {
      const shopify = this.context.getService('shopify');
      let dateFilter;
      
      switch (period) {
        case 'today':
          dateFilter = new Date().toISOString().split('T')[0];
          break;
        case 'week':
          dateFilter = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
          break;
        case 'month':
          dateFilter = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
          break;
        default:
          return 0;
      }
      
      const orders = await shopify.getOrders({
        created_at_min: dateFilter,
        status: 'any'
      });
      
      return orders.orders?.length || 0;
    } catch (error) {
      this.logger.error('Orders Count Fehler:', error);
      return 0;
    }
  }

  async getAverageOrderValue() {
    try {
      const shopify = this.context.getService('shopify');
      const monthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
      
      const orders = await shopify.getOrders({
        created_at_min: monthAgo,
        status: 'any'
      });
      
      if (!orders.orders || orders.orders.length === 0) return 0;
      
      const totalRevenue = orders.orders.reduce((sum, order) => sum + parseFloat(order.total_price), 0);
      return totalRevenue / orders.orders.length;
    } catch (error) {
      this.logger.error('AOV Fehler:', error);
      return 0;
    }
  }

  async getConversionRate() {
    // TODO: Implementieren mit echten Conversion-Daten
    return 0.0; // Placeholder
  }

  // Fallback-Dashboard wenn APIs nicht verfügbar
  getFallbackDashboard() {
    return {
      timestamp: new Date(),
      revenue: { today: 0, weekly: 0, monthly: 0 },
      costs: { today: 0, weekly: 0, monthly: 0 },
      profit: { today: 0, weekly: 0, monthly: 0 },
      metrics: {
        ordersToday: 0,
        ordersWeek: 0,
        ordersMonth: 0,
        avgOrderValue: 0,
        conversionRate: 0
      },
      status: 'fallback_mode'
    };
  }

  // Kosten-Killer Functions
  async getCostKillerReport() {
    try {
      const subscriptions = await this.getActiveSubscriptions();
      const cancellations = await this.getCancellationCandidates();
      
      const immediateSavings = cancellations
        .filter(c => c.action === 'cancel_immediately')
        .reduce((sum, c) => sum + c.monthlyCost, 0);
        
      const reviewSavings = cancellations
        .filter(c => c.action === 'review_for_downgrade')
        .reduce((sum, c) => sum + (c.potentialSavings || 0), 0);

      return {
        timestamp: new Date(),
        totalSubscriptions: subscriptions.length,
        totalMonthlyCosts: subscriptions.reduce((sum, s) => sum + s.monthlyCost, 0),
        cancellations: cancellations,
        savings: {
          immediate: {
            count: cancellations.filter(c => c.action === 'cancel_immediately').length,
            monthly: immediateSavings,
            yearly: immediateSavings * 12
          },
          review: {
            count: cancellations.filter(c => c.action === 'review_for_downgrade').length,
            monthly: reviewSavings,
            yearly: reviewSavings * 12
          },
          totalPotential: {
            monthly: immediateSavings + reviewSavings,
            yearly: (immediateSavings + reviewSavings) * 12
          }
        }
      };
    } catch (error) {
      this.logger.error('Cost Killer Report Fehler:', error);
      return { error: error.message };
    }
  }

  async getCancellationCandidates() {
    try {
      const subscriptions = await this.getActiveSubscriptions();
      const candidates = [];
      
      for (const sub of subscriptions) {
        const analysis = await this.analyzeSubscription(sub);
        if (analysis.shouldCancel || analysis.shouldDowngrade) {
          candidates.push({
            ...sub,
            analysis,
            action: analysis.shouldCancel ? 'cancel_immediately' : 'review_for_downgrade',
            potentialSavings: analysis.potentialSavings || 0
          });
        }
      }
      
      return candidates;
    } catch (error) {
      this.logger.error('Cancellation Candidates Fehler:', error);
      return [];
    }
  }

  async analyzeSubscription(subscription) {
    // TODO: Implementieren mit echtem Usage-Tracking
    const lastUsed = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000); // 90 Tage her
    const daysSinceLastUse = Math.floor((Date.now() - lastUsed) / (24 * 60 * 60 * 1000));
    
    return {
      shouldCancel: daysSinceLastUse > 60 && subscription.monthlyCost > 10,
      shouldDowngrade: daysSinceLastUse > 30 && subscription.monthlyCost > 5,
      lastUsed,
      daysSinceLastUse,
      potentialSavings: subscription.monthlyCost
    };
  }

  // Kritische Aktionen schützen
  async isCriticalAction(action) {
    const criticalActions = [
      'elster_submit',
      'tax_filing',
      'domain_delete',
      'hosting_cancel',
      'core_api_revoke',
      'security_key_rotate'
    ];
    
    return criticalActions.some(critical => action.toLowerCase().includes(critical));
  }

  // Revenue-First Job Filter
  filterJobsForRevenueFirst(jobs) {
    return jobs.filter(job => {
      const analysis = this.isRevenueFirst(job.name || job.description);
      return analysis.approved;
    }).sort((a, b) => {
      const priorityA = this.getPriority(a.name || a.description);
      const priorityB = this.getPriority(b.name || b.description);
      
      const priorityOrder = { 'HIGHEST': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3 };
      return priorityOrder[priorityA] - priorityOrder[priorityB];
    });
  }

  // Revenue-First Status Report
  async getRevenueFirstStatus() {
    const dashboard = await this.getRevenueDashboard();
    const costKiller = await this.getCostKillerReport();
    
    return {
      mode: 'REVENUE_FIRST',
      timestamp: new Date(),
      dashboard,
      costKiller,
      activeFocus: [
        'Shopify Orders & Revenue',
        'Payment Processing',
        'Cost Tracking',
        'Subscription Management',
        'Operational Stability'
      ],
      blocked: [
        'Demo Features',
        'Mockup Development',
        'Non-Essential Comfort Features'
      ]
    };
  }
}

module.exports = RevenueFirstMode;
