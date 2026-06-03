/**
 * Finance Revenue First Jobs
 * Echte Kostenkontrolle und Subscriptions Management
 */

class RevenueFirstFinance {
  constructor(orchestrator) {
    this.orchestrator = orchestrator;
    this.logger = orchestrator.logger;
    
    this.registerRevenueFirstJobs();
  }

  registerRevenueFirstJobs() {
    // HOCHSTE PRIORITÄT: Echte Cost Tracking
    this.orchestrator.registerJob('finance', 'track_real_costs', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '*/30 * * * *', // Alle 30 Minuten
      handler: this.trackRealCosts.bind(this),
      timeout: 120000,
      description: 'Echte Kosten in Echtzeit tracken'
    });

    this.orchestrator.registerJob('finance', 'sync_paypal_transactions', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '0 */2 * * *', // Alle 2 Stunden
      handler: this.syncPayPalTransactions.bind(this),
      timeout: 180000,
      description: 'PayPal Transaktionen syncen'
    });

    this.orchestrator.registerJob('finance', 'import_bank_transactions', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '0 6,18 * * *', // 6:00 und 18:00 Uhr
      handler: this.importBankTransactions.bind(this),
      timeout: 300000,
      description: 'Bank-Transaktionen importieren'
    });

    // HOHE PRIORITÄT: Subscriptions Management
    this.orchestrator.registerJob('finance', 'scan_active_subscriptions', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '0 */4 * * *', // Alle 4 Stunden
      handler: this.scanActiveSubscriptions.bind(this),
      timeout: 240000,
      description: 'Aktive Subscriptions scannen'
    });

    this.orchestrator.registerJob('finance', 'identify_cancellation_candidates', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '0 8 * * *', // Täglich 8:00 Uhr
      handler: this.identifyCancellationCandidates.bind(this),
      timeout: 180000,
      description: 'Kündigungs-Kandidaten identifizieren'
    });

    // APPROVE Jobs für Kündigungen
    this.orchestrator.registerJob('finance', 'cancel_subscription', {
      class: this.orchestrator.JOB_CLASSES.APPROVE,
      requiresApproval: true,
      handler: this.cancelSubscription.bind(this),
      timeout: 300000,
      description: 'Subscription kündigen (benötigt Approval)'
    });

    // MITTELRE PRIORITÄT: Cost Analytics
    this.orchestrator.registerJob('finance', 'generate_cost_report', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '0 20 * * *', // Täglich 20:00 Uhr
      handler: this.generateCostReport.bind(this),
      timeout: 240000,
      description: 'Cost Report generieren'
    });

    this.orchestrator.registerJob('finance', 'analyze_spending_trends', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '0 1 * * 1', // Wöchentlich Montag 1:00 Uhr
      handler: this.analyzeSpendingTrends.bind(this),
      timeout: 600000,
      description: 'Spending Trends analysieren'
    });

    this.logger.info('💰 Finance Revenue First Jobs registriert');
  }

  // ECHTE KOSTEN TRACKEN
  async trackRealCosts(context, executionId) {
    this.logger.info(`💸 Echte Kosten tracken (${executionId})`);
    
    try {
      const costs = {
        timestamp: new Date(),
        subscriptions: 0,
        transactions: 0,
        total: 0,
        breakdown: {}
      };

      // Subscriptions
      const subscriptions = await this.getActiveSubscriptions();
      costs.subscriptions = subscriptions.reduce((sum, sub) => sum + sub.monthlyCost, 0);
      
      // Heutige Transaktionen
      const todayTransactions = await this.getTodayTransactions();
      costs.transactions = todayTransactions.reduce((sum, tx) => sum + Math.abs(tx.amount), 0);
      
      costs.total = costs.subscriptions + costs.transactions;

      // Kosten-Breakdown
      costs.breakdown = {
        subscriptions: subscriptions.map(sub => ({
          name: sub.name,
          provider: sub.provider,
          monthlyCost: sub.monthlyCost,
          category: this.categorizeExpense(sub.name)
        })),
        transactions: todayTransactions.slice(0, 10).map(tx => ({
          description: tx.description,
          amount: Math.abs(tx.amount),
          category: this.categorizeExpense(tx.description)
        }))
      };

      // Kosten speichern
      await this.saveCostData(costs);

      // Event für hohe Kosten
      if (costs.total > 1000) { // Warnung bei > €1000/Tag
        this.orchestrator.emit('finance:high_costs', {
          total: costs.total,
          breakdown: costs.breakdown,
          executionId
        });
      }

      return {
        success: true,
        data: costs
      };
    } catch (error) {
      throw new Error(`Cost Tracking fehlgeschlagen: ${error.message}`);
    }
  }

  // PAYPAL TRANSAKTIONEN SYNC
  async syncPayPalTransactions(context, executionId) {
    this.logger.info(`💳 PayPal Transactions syncen (${executionId})`);
    
    try {
      const paypal = this.orchestrator.context.getService('paypal');
      const endDate = new Date();
      const startDate = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000); // Letzte 2 Tage
      
      const transactions = await paypal.getTransactions(startDate, endDate);
      
      if (!transactions || !transactions.transaction_details) {
        return {
          success: true,
          data: { synced: 0, transactions: [] }
        };
      }

      const syncedTransactions = [];
      
      for (const tx of transactions.transaction_details) {
        const processed = await this.processPayPalTransaction(tx);
        if (processed.isNew) {
          syncedTransactions.push(processed);
        }
      }

      // Sync-Report
      const report = {
        timestamp: new Date(),
        period: { from: startDate, to: endDate },
        synced: syncedTransactions.length,
        total: transactions.transaction_details.length,
        transactions: syncedTransactions
      };

      await this.savePayPalSyncReport(report);

      return {
        success: true,
        data: report
      };
    } catch (error) {
      throw new Error(`PayPal Sync fehlgeschlagen: ${error.message}`);
    }
  }

  // BANK TRANSAKTIONEN IMPORT
  async importBankTransactions(context, executionId) {
    this.logger.info(`🏦 Bank-Transaktionen importieren (${executionId})`);
    
    try {
      const bank = this.orchestrator.context.getService('bank');
      const today = new Date().toISOString().split('T')[0];
      const filename = `transactions_${today}.csv`;
      
      let transactions = [];
      
      try {
        transactions = await bank.importCSV(filename);
      } catch (error) {
        // Wenn keine neue Datei, letzte verwenden
        const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        const yesterdayFile = `transactions_${yesterday}.csv`;
        
        try {
          transactions = await bank.importCSV(yesterdayFile);
        } catch (yesterdayError) {
          return {
            success: true,
            data: { imported: 0, message: 'Keine Bank-Transaktionen gefunden' }
          };
        }
      }

      const processedTransactions = [];
      
      for (const tx of transactions) {
        const processed = await this.processBankTransaction(tx);
        if (processed.isNew) {
          processedTransactions.push(processed);
        }
      }

      const report = {
        timestamp: new Date(),
        filename,
        imported: processedTransactions.length,
        total: transactions.length,
        transactions: processedTransactions
      };

      await this.saveBankImportReport(report);

      return {
        success: true,
        data: report
      };
    } catch (error) {
      throw new Error(`Bank Import fehlgeschlagen: ${error.message}`);
    }
  }

  // AKTIVE SUBSCRIPTIONS SCANNEN
  async scanActiveSubscriptions(context, executionId) {
    this.logger.info(`🔍 Aktive Subscriptions scannen (${executionId})`);
    
    try {
      const subscriptions = await this.getActiveSubscriptions();
      
      const analysis = {
        timestamp: new Date(),
        total: subscriptions.length,
        totalMonthlyCost: subscriptions.reduce((sum, sub) => sum + sub.monthlyCost, 0),
        byProvider: {},
        byCategory: {},
        atRisk: [],
        upcoming: []
      };

      subscriptions.forEach(sub => {
        // By Provider
        if (!analysis.byProvider[sub.provider]) {
          analysis.byProvider[sub.provider] = { count: 0, cost: 0 };
        }
        analysis.byProvider[sub.provider].count += 1;
        analysis.byProvider[sub.provider].cost += sub.monthlyCost;
        
        // By Category
        const category = this.categorizeExpense(sub.name);
        if (!analysis.byCategory[category]) {
          analysis.byCategory[category] = { count: 0, cost: 0 };
        }
        analysis.byCategory[category].count += 1;
        analysis.byCategory[category].cost += sub.monthlyCost;
        
        // Risk Analysis
        const risk = await this.analyzeSubscriptionRisk(sub);
        if (risk.atRisk) {
          analysis.atRisk.push({ ...sub, risk });
        }
        
        // Upcoming Billing
        if (sub.nextBilling) {
          const daysUntil = Math.floor((new Date(sub.nextBilling) - new Date()) / (24 * 60 * 60 * 1000));
          if (daysUntil <= 7 && daysUntil >= 0) {
            analysis.upcoming.push({ ...sub, daysUntil });
          }
        }
      });

      // Analysis speichern
      await this.saveSubscriptionAnalysis(analysis);

      // Event für Risk-Subscriptions
      if (analysis.atRisk.length > 0) {
        this.orchestrator.emit('finance:risk_subscriptions', {
          atRisk: analysis.atRisk,
          totalSavings: analysis.atRisk.reduce((sum, sub) => sum + sub.monthlyCost, 0),
          executionId
        });
      }

      return {
        success: true,
        data: analysis
      };
    } catch (error) {
      throw new Error(`Subscription Scan fehlgeschlagen: ${error.message}`);
    }
  }

  // KÜNDIGUNGS-KANDIDATEN IDENTIFIZIEREN
  async identifyCancellationCandidates(context, executionId) {
    this.logger.info(`🎯 Kündigungs-Kandidaten identifizieren (${executionId})`);
    
    try {
      const subscriptions = await this.getActiveSubscriptions();
      const candidates = [];
      
      for (const sub of subscriptions) {
        const analysis = await this.analyzeForCancellation(sub);
        
        if (analysis.shouldCancel || analysis.shouldDowngrade) {
          candidates.push({
            ...sub,
            analysis,
            action: analysis.shouldCancel ? 'CANCEL_IMMEDIATELY' : 'DOWNGRADE_REVIEW',
            priority: analysis.priority,
            potentialSavings: analysis.potentialSavings || 0
          });
        }
      }

      // Nach Priorität sortieren
      candidates.sort((a, b) => (b.potentialSavings || 0) - (a.potentialSavings || 0));

      const report = {
        timestamp: new Date(),
        totalCandidates: candidates.length,
        immediateCancellations: candidates.filter(c => c.action === 'CANCEL_IMMEDIATELY'),
        downgradeReviews: candidates.filter(c => c.action === 'DOWNGRADE_REVIEW'),
        totalPotentialSavings: candidates.reduce((sum, c) => sum + (c.potentialSavings || 0), 0),
        candidates: candidates
      };

      await this.saveCancellationReport(report);

      // Event für hohe Einsparungen
      const highSavings = candidates.filter(c => c.potentialSavings > 50);
      if (highSavings.length > 0) {
        this.orchestrator.emit('finance:high_savings_opportunity', {
          opportunities: highSavings,
          totalSavings: highSavings.reduce((sum, c) => sum + (c.potentialSavings || 0), 0),
          executionId
        });
      }

      return {
        success: true,
        data: report
      };
    } catch (error) {
      throw new Error(`Kündigungs-Analyse fehlgeschlagen: ${error.message}`);
    }
  }

  // SUBSCRIPTION KÜNDIGEN (APPROVE JOB)
  async cancelSubscription(context, executionId) {
    this.logger.info(`❌ Subscription kündigen (${executionId})`);
    
    const { subscriptionId, provider, reason } = context;
    
    if (!subscriptionId || !provider) {
      throw new Error('subscriptionId und provider erforderlich');
    }

    try {
      let result;
      
      switch (provider.toLowerCase()) {
        case 'paypal':
          result = await this.cancelPayPalSubscription(subscriptionId, reason);
          break;
        case 'stripe':
          result = await this.cancelStripeSubscription(subscriptionId, reason);
          break;
        default:
          throw new Error(`Provider ${provider} nicht unterstützt`);
      }

      // Event für Kündigung
      this.orchestrator.emit('finance:subscription_cancelled', {
        subscriptionId,
        provider,
        reason,
        result,
        executionId
      });

      return {
        success: true,
        data: {
          subscriptionId,
          provider,
          cancelledAt: new Date(),
          result
        }
      };
    } catch (error) {
      throw new Error(`Subscription Kündigung fehlgeschlagen: ${error.message}`);
    }
  }

  // COST REPORT GENERIEREN
  async generateCostReport(context, executionId) {
    this.logger.info(`📊 Cost Report generieren (${executionId})`);
    
    try {
      const today = new Date();
      const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
      const monthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
      
      const report = {
        timestamp: today,
        periods: {
          today: await this.getCostsForPeriod(today, today),
          week: await this.getCostsForPeriod(weekAgo, today),
          month: await this.getCostsForPeriod(monthAgo, today)
        },
        subscriptions: await this.getActiveSubscriptions(),
        trends: await this.calculateCostTrends(),
        recommendations: await this.generateCostRecommendations()
      };

      // Report speichern
      await this.saveCostReport(report);

      // Event für hohe Kosten
      if (report.periods.month.total > 5000) {
        this.orchestrator.emit('finance:high_monthly_costs', {
          total: report.periods.month.total,
          report,
          executionId
        });
      }

      return {
        success: true,
        data: report
      };
    } catch (error) {
      throw new Error(`Cost Report fehlgeschlagen: ${error.message}`);
    }
  }

  // SPENDING TRENDS ANALYSIEREN
  async analyzeSpendingTrends(context, executionId) {
    this.logger.info(`📈 Spending Trends analysieren (${executionId})`);
    
    try {
      const trends = {
        timestamp: new Date(),
        period: '4_weeks',
        weeklyData: [],
        categories: {},
        insights: [],
        forecast: {}
      };

      // Letzte 4 Wochen analysieren
      for (let i = 3; i >= 0; i--) {
        const weekStart = new Date(Date.now() - (i + 1) * 7 * 24 * 60 * 60 * 1000);
        const weekEnd = new Date(Date.now() - i * 7 * 24 * 60 * 60 * 1000);
        
        const weekData = this.getCostsForPeriod(weekStart, weekEnd);
        weekData.week = i + 1;
        weekData.period = `${weekStart.toISOString().split('T')[0]} - ${weekEnd.toISOString().split('T')[0]}`;
        
        trends.weeklyData.push(weekData);
      }

      // Category Trends
      trends.weeklyData.forEach(week => {
        Object.keys(week.byCategory).forEach(category => {
          if (!trends.categories[category]) {
            trends.categories[category] = [];
          }
          trends.categories[category].push(week.byCategory[category]);
        });
      });

      // Insights generieren
      trends.insights = this.generateSpendingInsights(trends);
      
      // Forecast für nächste Woche
      trends.forecast = this.forecastNextWeek(trends.weeklyData);

      await this.saveSpendingTrends(trends);

      return {
        success: true,
        data: trends
      };
    } catch (error) {
      throw new Error(`Spending Trends Analyse fehlgeschlagen: ${error.message}`);
    }
  }

  // Helper Functions
  async getActiveSubscriptions() {
    try {
      const paypal = this.orchestrator.context.getService('paypal');
      const subscriptions = await paypal.getSubscriptions();
      
      return subscriptions.map(sub => ({
        id: sub.id,
        name: sub.description || 'Unknown Subscription',
        provider: 'PayPal',
        monthlyCost: parseFloat(sub.amount.total),
        status: sub.status,
        nextBilling: sub.next_billing_time,
        created: sub.create_time
      }));
    } catch (error) {
      this.logger.error('Active Subscriptions Fehler:', error);
      return [];
    }
  }

  async getTodayTransactions() {
    // TODO: Implementieren mit echtem Transaction-Tracking
    return [];
  }

  categorizeExpense(description) {
    const desc = description.toLowerCase();
    
    if (desc.includes('shopify') || desc.includes('ecommerce')) return 'ecommerce';
    if (desc.includes('hosting') || desc.includes('server')) return 'infrastructure';
    if (desc.includes('software') || desc.includes('app')) return 'software';
    if (desc.includes('marketing') || desc.includes('ads')) return 'marketing';
    if (desc.includes('office') || desc.includes('equipment')) return 'office';
    
    return 'other';
  }

  async analyzeSubscriptionRisk(subscription) {
    // TODO: Implementieren mit echtem Usage-Tracking
    const daysSinceCreation = Math.floor((Date.now() - new Date(subscription.created).getTime()) / (24 * 60 * 60 * 1000));
    
    return {
      atRisk: subscription.monthlyCost > 100 && daysSinceCreation > 90,
      riskScore: subscription.monthlyCost / 10,
      lastUsed: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
    };
  }

  async analyzeForCancellation(subscription) {
    const risk = await this.analyzeSubscriptionRisk(subscription);
    
    return {
      shouldCancel: risk.atRisk && subscription.monthlyCost > 50,
      shouldDowngrade: risk.riskScore > 5 && subscription.monthlyCost > 20,
      priority: risk.riskScore > 10 ? 'HIGH' : 'MEDIUM',
      potentialSavings: subscription.monthlyCost,
      reason: risk.atRisk ? 'Nicht genutzt und hohe Kosten' : 'Redundant oder zu teuer'
    };
  }

  async cancelPayPalSubscription(subscriptionId, reason) {
    const paypal = this.orchestrator.context.getService('paypal');
    return await paypal.fetch(`/v1/billing/subscriptions/${subscriptionId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'Cost optimization' })
    });
  }

  async cancelStripeSubscription(subscriptionId, reason) {
    // TODO: Implementieren mit echtem Stripe-Client
    return { cancelled: true, id: subscriptionId };
  }

  async processPayPalTransaction(transaction) {
    // TODO: Implementieren mit echtem Transaction-Processing
    return {
      id: transaction.transaction_id,
      isNew: true,
      amount: parseFloat(transaction.amount.value),
      description: transaction.note
    };
  }

  async processBankTransaction(transaction) {
    // TODO: Implementieren mit echtem Transaction-Processing
    return {
      id: `bank_${Date.now()}_${Math.random()}`,
      isNew: true,
      amount: transaction.amount,
      description: transaction.description
    };
  }

  getCostsForPeriod(startDate, endDate) {
    // TODO: Implementieren mit echtem Cost-Aggregation
    return Promise.resolve({
      period: `${startDate.toISOString().split('T')[0]} - ${endDate.toISOString().split('T')[0]}`,
      total: 0,
      subscriptions: 0,
      transactions: 0,
      byCategory: {}
    });
  }

  async calculateCostTrends() {
    // TODO: Implementieren mit echten Trend-Analysen
    return {
      direction: 'stable',
      changePercent: 0,
      confidence: 'low'
    };
  }

  async generateCostRecommendations() {
    // TODO: Implementieren mit echten Recommendations
    return [
      'Review unused subscriptions',
      'Negotiate better rates',
      'Consider annual billing'
    ];
  }

  generateSpendingInsights(trends) {
    // TODO: Implementieren mit echten Insights
    return [
      'Spending increased by 15% this week',
      'Software costs are trending upward'
    ];
  }

  forecastNextWeek(weeklyData) {
    // TODO: Implementieren mit echtem Forecasting
    const avgWeekly = weeklyData.reduce((sum, week) => sum + week.total, 0) / weeklyData.length;
    return {
      predicted: avgWeekly,
      confidence: 'medium',
      range: { min: avgWeekly * 0.8, max: avgWeekly * 1.2 }
    };
  }

  // Storage Functions (Platzhalter)
  async saveCostData(costs) {
    this.logger.info(`💾 Cost Daten gespeichert: €${costs.total}`);
  }

  async savePayPalSyncReport(report) {
    this.logger.info(`💾 PayPal Sync Report gespeichert: ${report.synced} Transactions`);
  }

  async saveBankImportReport(report) {
    this.logger.info(`💾 Bank Import Report gespeichert: ${report.imported} Transactions`);
  }

  async saveSubscriptionAnalysis(analysis) {
    this.logger.info(`💾 Subscription Analysis gespeichert: ${analysis.total} Subscriptions`);
  }

  async saveCancellationReport(report) {
    this.logger.info(`💾 Cancellation Report gespeichert: ${report.totalCandidates} Candidates`);
  }

  async saveCostReport(report) {
    this.logger.info(`💾 Cost Report gespeichert: €${report.periods.month.total} Monthly`);
  }

  async saveSpendingTrends(trends) {
    this.logger.info(`💾 Spending Trends gespeichert: ${trends.weeklyData.length} Weeks`);
  }
}

module.exports = RevenueFirstFinance;
