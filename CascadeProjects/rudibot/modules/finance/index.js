/**
 * Finance Module
 * Kosten, PayPal, Bank, Subscriptions
 */

const Orchestrator = require('../../core/orchestrator');

class FinanceModule {
  constructor(orchestrator) {
    this.orchestrator = orchestrator;
    this.logger = orchestrator.logger;
    this.name = 'finance';
    
    this.registerJobs();
  }

  registerJobs() {
    // PayPal Jobs
    this.orchestrator.registerJob('finance', 'import_paypal', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '*/15 * * * *', // Alle 15 Minuten
      handler: this.importPayPalTransactions.bind(this),
      timeout: 90000
    });

    this.orchestrator.registerJob('finance', 'sync_paypal_subscriptions', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 */6 * * *', // Alle 6 Stunden
      handler: this.syncPayPalSubscriptions.bind(this),
      timeout: 120000
    });

    // Bank Jobs
    this.orchestrator.registerJob('finance', 'import_bank_transactions', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 */4 * * *', // Alle 4 Stunden
      handler: this.importBankTransactions.bind(this),
      timeout: 60000
    });

    this.orchestrator.registerJob('finance', 'reconcile_bank_statements', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 2 * * *', // Täglich 2:00 Uhr
      handler: this.reconcileBankStatements.bind(this),
      timeout: 300000
    });

    // Subscription Jobs
    this.orchestrator.registerJob('finance', 'scan_subscriptions', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 9 * * *', // Täglich 9:00 Uhr
      handler: this.scanSubscriptions.bind(this),
      timeout: 180000
    });

    this.orchestrator.registerJob('finance', 'cancel_subscription', {
      class: Orchestrator.prototype.JOB_CLASSES.APPROVE,
      requiresApproval: true,
      handler: this.cancelSubscription.bind(this),
      timeout: 60000
    });

    // Cost Analysis Jobs
    this.orchestrator.registerJob('finance', 'analyze_costs', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 20 * * *', // Täglich 20:00 Uhr
      handler: this.analyzeCosts.bind(this),
      timeout: 120000
    });

    this.orchestrator.registerJob('finance', 'cost_killer_report', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 8 * * 1', // Montags 8:00 Uhr
      handler: this.generateCostKillerReport.bind(this),
      timeout: 90000
    });

    // Financial Planning Jobs
    this.orchestrator.registerJob('finance', 'monthly_forecast', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 6 1 * *', // Erster des Monats 6:00 Uhr
      handler: this.generateMonthlyForecast.bind(this),
      timeout: 240000
    });

    this.logger.info('💰 Finance Module Jobs registriert');
  }

  // PayPal Transactions Import
  async importPayPalTransactions(context, executionId) {
    this.logger.info(`💳 PayPal Transactions Import (${executionId})`);
    
    try {
      const paypal = require('../paypal/client');
      const startDate = this.getStartDate(context);
      const endDate = new Date().toISOString();
      
      const transactions = await paypal.getTransactions(startDate, endDate);
      
      let imported = 0;
      let duplicates = 0;
      let errors = 0;

      for (const transaction of transactions) {
        try {
          const existing = await this.findTransactionByPayPalId(transaction.id);
          
          if (existing) {
            duplicates++;
          } else {
            await this.savePayPalTransaction(transaction);
            imported++;
            
            // Events für wichtige Transaktionen
            if (transaction.type === 'payment' && parseFloat(transaction.amount) > 100) {
              this.orchestrator.emit('payment:received', {
                source: 'paypal',
                transaction,
                executionId
              });
            }
          }
        } catch (error) {
          this.logger.error(`Fehler bei PayPal Transaction ${transaction.id}:`, error.message);
          errors++;
        }
      }

      return {
        success: true,
        data: {
          total: transactions.length,
          imported,
          duplicates,
          errors,
          period: { startDate, endDate },
          executionId
        }
      };
    } catch (error) {
      throw new Error(`PayPal Import fehlgeschlagen: ${error.message}`);
    }
  }

  // PayPal Subscriptions Sync
  async syncPayPalSubscriptions(context, executionId) {
    this.logger.info(`🔄 PayPal Subscriptions Sync (${executionId})`);
    
    try {
      const paypal = require('../paypal/client');
      const subscriptions = await paypal.getAllSubscriptions();
      
      let updated = 0;
      let cancelled = 0;
      let created = 0;

      for (const subscription of subscriptions) {
        const existing = await this.findSubscriptionByPayPalId(subscription.id);
        
        if (existing) {
          if (existing.status !== subscription.status) {
            await this.updateSubscriptionStatus(existing.id, subscription.status);
            updated++;
            
            if (subscription.status === 'CANCELLED') {
              cancelled++;
              this.orchestrator.emit('subscription:cancelled', {
                source: 'paypal',
                subscription,
                executionId
              });
            }
          }
        } else {
          await this.createSubscription(subscription);
          created++;
        }
      }

      return {
        success: true,
        data: {
          total: subscriptions.length,
          updated,
          cancelled,
          created,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`PayPal Subscriptions Sync fehlgeschlagen: ${error.message}`);
    }
  }

  // Bank Transactions Import
  async importBankTransactions(context, executionId) {
    this.logger.info(`🏦 Bank Transactions Import (${executionId})`);
    
    try {
      const bank = require('../bank/client');
      const startDate = this.getStartDate(context);
      const endDate = new Date().toISOString();
      
      const transactions = await bank.getTransactions(startDate, endDate);
      
      let imported = 0;
      let duplicates = 0;

      for (const transaction of transactions) {
        const existing = await this.findTransactionByBankId(transaction.id);
        
        if (!existing) {
          await this.saveBankTransaction(transaction);
          imported++;
          
          // Events für wichtige Banktransaktionen
          if (transaction.amount > 1000) {
            this.orchestrator.emit('bank:large_transaction', {
              transaction,
              executionId
            });
          }
        } else {
          duplicates++;
        }
      }

      return {
        success: true,
        data: {
          total: transactions.length,
          imported,
          duplicates,
          period: { startDate, endDate },
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Bank Import fehlgeschlagen: ${error.message}`);
    }
  }

  // Bank Statements Reconciliation
  async reconcileBankStatements(context, executionId) {
    this.logger.info(`🔍 Bank Statements Reconciliation (${executionId})`);
    
    try {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const date = yesterday.toISOString().split('T')[0];
      
      // Shopify Umsätze
      const shopifyRevenue = await this.getShopifyRevenue(date);
      
      // PayPal Transaktionen
      const paypalTransactions = await this.getPayPalTransactions(date);
      
      // Bank Transaktionen
      const bankTransactions = await this.getBankTransactions(date);
      
      // Reconciliation durchführen
      const reconciliation = {
        date,
        shopifyRevenue,
        paypalRevenue: paypalTransactions.reduce((sum, t) => sum + t.amount, 0),
        bankRevenue: bankTransactions.filter(t => t.amount > 0).reduce((sum, t) => sum + t.amount, 0),
        discrepancies: []
      };

      // Diskrepanzen prüfen
      const expectedRevenue = reconciliation.shopifyRevenue + reconciliation.paypalRevenue;
      const actualRevenue = reconciliation.bankRevenue;
      
      if (Math.abs(expectedRevenue - actualRevenue) > 10) {
        reconciliation.discrepancies.push({
          type: 'revenue_mismatch',
          expected: expectedRevenue,
          actual: actualRevenue,
          difference: expectedRevenue - actualRevenue
        });
      }

      // Reconciliation speichern
      await this.saveReconciliation(reconciliation);

      return {
        success: true,
        data: reconciliation
      };
    } catch (error) {
      throw new Error(`Bank Reconciliation fehlgeschlagen: ${error.message}`);
    }
  }

  // Subscription Scanning
  async scanSubscriptions(context, executionId) {
    this.logger.info(`🔍 Subscription Scan (${executionId})`);
    
    try {
      const subscriptions = await this.getAllSubscriptions();
      const analysis = {
        total: subscriptions.length,
        active: 0,
        cancelled: 0,
        totalMonthlyCost: 0,
        upcomingCancellations: [],
        unusedSubscriptions: [],
        expensiveSubscriptions: []
      };

      for (const subscription of subscriptions) {
        if (subscription.status === 'ACTIVE') {
          analysis.active++;
          analysis.totalMonthlyCost += subscription.monthly_cost;
          
          // Teure Abos markieren (>100€/Monat)
          if (subscription.monthly_cost > 100) {
            analysis.expensiveSubscriptions.push({
              id: subscription.id,
              name: subscription.name,
              cost: subscription.monthly_cost
            });
          }
          
          // Unbenutzte Abos prüfen
          const lastUsage = await this.getLastUsage(subscription.id);
          if (lastUsage && new Date(lastUsage) < new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)) {
            analysis.unusedSubscriptions.push({
              id: subscription.id,
              name: subscription.name,
              cost: subscription.monthly_cost,
              lastUsage
            });
          }
        } else {
          analysis.cancelled++;
        }
      }

      // Event für hohe Kosten
      if (analysis.totalMonthlyCost > 500) {
        this.orchestrator.emit('subscription:high_cost', {
          totalCost: analysis.totalMonthlyCost,
          analysis,
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

  // Subscription Cancellation (APPROVE Job)
  async cancelSubscription(context, executionId) {
    this.logger.info(`❌ Subscription Cancellation (${executionId})`);
    
    const { subscriptionId, reason, immediate } = context;
    
    if (!subscriptionId) {
      throw new Error('subscriptionId erforderlich');
    }

    try {
      const subscription = await this.getSubscription(subscriptionId);
      if (!subscription) {
        throw new Error(`Subscription ${subscriptionId} nicht gefunden`);
      }

      let result;
      
      if (subscription.source === 'paypal') {
        const paypal = require('../paypal/client');
        result = await paypal.cancelSubscription(subscriptionId, immediate);
      } else if (subscription.source === 'stripe') {
        const stripe = require('../stripe/client');
        result = await stripe.cancelSubscription(subscriptionId, immediate);
      } else {
        throw new Error(`Subscription source ${subscription.source} nicht unterstützt`);
      }

      // Lokalen Status aktualisieren
      await this.updateSubscriptionStatus(subscriptionId, 'CANCELLED');

      // Event emittieren
      this.orchestrator.emit('subscription:cancelled', {
        subscriptionId,
        reason,
        immediate,
        result,
        executionId
      });

      return {
        success: true,
        data: {
          subscriptionId,
          status: 'CANCELLED',
          reason,
          result,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Subscription Cancellation fehlgeschlagen: ${error.message}`);
    }
  }

  // Cost Analysis
  async analyzeCosts(context, executionId) {
    this.logger.info(`📊 Cost Analysis (${executionId})`);
    
    try {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const date = yesterday.toISOString().split('T')[0];
      
      // Kosten sammeln
      const costs = {
        date,
        subscriptions: await this.getSubscriptionCosts(date),
        infrastructure: await this.getInfrastructureCosts(date),
        marketing: await this.getMarketingCosts(date),
        other: await this.getOtherCosts(date),
        total: 0
      };

      costs.total = costs.subscriptions + costs.infrastructure + costs.marketing + costs.other;

      // Vergleich mit Vormonat
      const lastMonth = await this.getCostAnalysisLastMonth(date);
      const comparison = {
        current: costs.total,
        previous: lastMonth?.total || 0,
        change: costs.total - (lastMonth?.total || 0),
        changePercent: lastMonth?.total ? ((costs.total - lastMonth.total) / lastMonth.total * 100) : 0
      };

      // Analyse speichern
      await this.saveCostAnalysis(costs);

      // Event für signifikante Kostenänderungen
      if (Math.abs(comparison.changePercent) > 20) {
        this.orchestrator.emit('costs:significant_change', {
          costs,
          comparison,
          executionId
        });
      }

      return {
        success: true,
        data: {
          costs,
          comparison,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Cost Analysis fehlgeschlagen: ${error.message}`);
    }
  }

  // Cost Killer Report
  async generateCostKillerReport(context, executionId) {
    this.logger.info(`⚔️ Cost Killer Report (${executionId})`);
    
    try {
      const lastMonth = new Date();
      lastMonth.setMonth(lastMonth.getMonth() - 1);
      
      // Kosten der letzten 30 Tage
      const costs = await this.getCostsLast30Days();
      const subscriptions = await this.getAllSubscriptions();
      
      const report = {
        period: 'Letzte 30 Tage',
        totalCosts: costs.total,
        breakdown: costs,
        recommendations: [],
        potentialSavings: 0
      };

      // Unbenutzte Abos identifizieren
      const unusedSubs = subscriptions.filter(sub => {
        const lastUsage = this.getLastUsage(sub.id);
        return lastUsage && new Date(lastUsage) < new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
      });

      // Empfehlungen generieren
      for (const sub of unusedSubs) {
        report.recommendations.push({
          type: 'cancel_subscription',
          target: sub.name,
          monthlySavings: sub.monthly_cost,
          reason: 'Nicht seit 30+ Tagen genutzt',
          action: 'cancel_subscription',
          requiresApproval: true
        });
        
        report.potentialSavings += sub.monthly_cost;
      }

      // Teure Abos prüfen
      const expensiveSubs = subscriptions.filter(sub => sub.monthly_cost > 100);
      for (const sub of expensiveSubs) {
        report.recommendations.push({
          type: 'review_subscription',
          target: sub.name,
          monthlyCost: sub.monthly_cost,
          reason: 'Hohe monatliche Kosten',
          action: 'review_usage'
        });
      }

      // Report speichern
      await this.saveCostKillerReport(report);

      // Event emittieren
      this.orchestrator.emit('report:generated', {
        type: 'cost_killer',
        report,
        executionId
      });

      return {
        success: true,
        data: report
      };
    } catch (error) {
      throw new Error(`Cost Killer Report fehlgeschlagen: ${error.message}`);
    }
  }

  // Monthly Forecast
  async generateMonthlyForecast(context, executionId) {
    this.logger.info(`📈 Monthly Forecast (${executionId})`);
    
    try {
      const currentMonth = new Date().toISOString().slice(0, 7);
      
      // Historische Daten sammeln
      const historicalData = await this.getHistoricalRevenue(6); // Letzte 6 Monate
      const currentSubscriptions = await this.getAllSubscriptions();
      
      // Prognose berechnen
      const forecast = {
        month: currentMonth,
        revenue: this.calculateRevenueForecast(historicalData),
        costs: this.calculateCostForecast(currentSubscriptions),
        profit: 0,
        confidence: 0.8
      };

      forecast.profit = forecast.revenue - forecast.costs;

      // Forecast speichern
      await this.saveMonthlyForecast(forecast);

      return {
        success: true,
        data: forecast
      };
    } catch (error) {
      throw new Error(`Monthly Forecast fehlgeschlagen: ${error.message}`);
    }
  }

  // Helper Functions
  getStartDate(context) {
    if (context.startDate) return context.startDate;
    
    const defaultStart = new Date();
    defaultStart.setHours(defaultStart.getHours() - 24); // Letzte 24 Stunden
    return defaultStart.toISOString();
  }

  calculateRevenueForecast(historicalData) {
    if (historicalData.length < 2) return 0;
    
    // Einfache lineare Regression
    const n = historicalData.length;
    const sumX = historicalData.reduce((sum, _, i) => sum + i, 0);
    const sumY = historicalData.reduce((sum, data) => sum + data.revenue, 0);
    const sumXY = historicalData.reduce((sum, data, i) => sum + i * data.revenue, 0);
    const sumX2 = historicalData.reduce((sum, _, i) => sum + i * i, 0);
    
    const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;
    
    // Nächsten Monat prognostizieren
    return slope * n + intercept;
  }

  calculateCostForecast(subscriptions) {
    return subscriptions
      .filter(sub => sub.status === 'ACTIVE')
      .reduce((sum, sub) => sum + sub.monthly_cost, 0);
  }

  // Database Helper Functions (Platzhalter)
  async findTransactionByPayPalId(id) {
    // TODO: Implementieren mit echter DB
    return null;
  }

  async savePayPalTransaction(transaction) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`💳 PayPal Transaction gespeichert: ${transaction.id}`);
  }

  async findSubscriptionByPayPalId(id) {
    // TODO: Implementieren mit echter DB
    return null;
  }

  async createSubscription(subscription) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`📝 Subscription erstellt: ${subscription.id}`);
  }

  async updateSubscriptionStatus(id, status) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`📝 Subscription Status aktualisiert: ${id} -> ${status}`);
  }

  async findTransactionByBankId(id) {
    // TODO: Implementieren mit echter DB
    return null;
  }

  async saveBankTransaction(transaction) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`🏦 Bank Transaction gespeichert: ${transaction.id}`);
  }

  async getShopifyRevenue(date) {
    // TODO: Implementieren mit echter DB
    return 0;
  }

  async getPayPalTransactions(date) {
    // TODO: Implementieren mit echter DB
    return [];
  }

  async getBankTransactions(date) {
    // TODO: Implementieren mit echter DB
    return [];
  }

  async saveReconciliation(reconciliation) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`🔍 Reconciliation gespeichert: ${reconciliation.date}`);
  }

  async getAllSubscriptions() {
    // TODO: Implementieren mit echter DB
    return [];
  }

  async getLastUsage(subscriptionId) {
    // TODO: Implementieren mit echter DB
    return null;
  }

  async getSubscription(subscriptionId) {
    // TODO: Implementieren mit echter DB
    return null;
  }

  async getSubscriptionCosts(date) {
    // TODO: Implementieren mit echter DB
    return 0;
  }

  async getInfrastructureCosts(date) {
    // TODO: Implementieren mit echter DB
    return 0;
  }

  async getMarketingCosts(date) {
    // TODO: Implementieren mit echter DB
    return 0;
  }

  async getOtherCosts(date) {
    // TODO: Implementieren mit echter DB
    return 0;
  }

  async getCostAnalysisLastMonth(date) {
    // TODO: Implementieren mit echter DB
    return null;
  }

  async saveCostAnalysis(costs) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`💸 Cost Analysis gespeichert: ${costs.date}`);
  }

  async getCostsLast30Days() {
    // TODO: Implementieren mit echter DB
    return { total: 0, subscriptions: 0, infrastructure: 0, marketing: 0, other: 0 };
  }

  async saveCostKillerReport(report) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`⚔️ Cost Killer Report gespeichert`);
  }

  async getHistoricalRevenue(months) {
    // TODO: Implementieren mit echter DB
    return [];
  }

  async saveMonthlyForecast(forecast) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`📈 Monthly Forecast gespeichert: ${forecast.month}`);
  }
}

module.exports = FinanceModule;
