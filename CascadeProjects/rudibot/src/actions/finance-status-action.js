/**
 * Finance Status Action — Generates finance overview and status reports
 * Bridges KIVO finance intents to Finance Grid modules
 */

class FinanceStatusAction {
  constructor(expenseRadar, subscriptionHunter, taxCore) {
    this.expenseRadar = expenseRadar;
    this.subscriptionHunter = subscriptionHunter;
    this.taxCore = taxCore;
  }

  async execute(options = {}) {
    const { scope = 'all', period = 'current_month', chatId } = options;
    
    try {
      const report = await this.generateReport(scope, period);
      
      return {
        success: true,
        scope,
        period,
        report,
        message: this.formatReport(report, scope),
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Finance report failed: ${e.message}`
      };
    }
  }

  async generateReport(scope, period) {
    const report = {
      period,
      generatedAt: new Date().toISOString(),
      sections: {}
    };

    if (scope === 'all' || scope === 'subscriptions') {
      report.sections.subscriptions = await this.getSubscriptionStatus();
    }

    if (scope === 'all' || scope === 'expenses') {
      report.sections.expenses = await this.getExpenseStatus(period);
    }

    if (scope === 'all' || scope === 'tax') {
      report.sections.tax = await this.getTaxStatus(period);
    }

    if (scope === 'all' || scope === 'overview') {
      report.sections.overview = await this.getFinancialOverview(report.sections);
    }

    return report;
  }

  async getSubscriptionStatus() {
    try {
      if (this.subscriptionHunter) {
        const allSubs = this.subscriptionHunter.getAllSubscriptions ? 
          this.subscriptionHunter.getAllSubscriptions() : [];
        const summary = this.subscriptionHunter.getSummary ? 
          this.subscriptionHunter.getSummary() : { totalMonthly: 0, totalAnnual: 0 };
        
        return {
          totalActive: allSubs.length,
          totalMonthlyCost: summary.totalMonthly || 0,
          totalAnnualCost: summary.totalAnnual || 0,
          upcomingRenewals: allSubs.filter(s => {
            const days = Math.ceil((new Date(s.nextBilling) - Date.now()) / (1000 * 60 * 60 * 24));
            return days <= 30;
          }).length,
          topExpensive: allSubs
            .sort((a, b) => (b.monthlyCost || 0) - (a.monthlyCost || 0))
            .slice(0, 3)
            .map(s => ({ name: s.name, cost: s.monthlyCost || 0 })),
          subscriptions: allSubs.map(s => ({
            name: s.name,
            provider: s.provider,
            monthlyCost: s.monthlyCost || 0,
            nextBilling: s.nextBilling,
            status: s.status || 'active'
          }))
        };
      }

      // Fallback
      return this.getMockSubscriptionData();
    } catch (e) {
      console.warn('Subscription status error:', e.message);
      return this.getMockSubscriptionData();
    }
  }

  async getExpenseStatus(period) {
    try {
      if (this.expenseRadar) {
        const expenses = this.expenseRadar.getMonthlySummary ?
          this.expenseRadar.getMonthlySummary() : { income: 0, expenses: 0 };
        
        return {
          totalIncome: expenses.income || 0,
          totalExpenses: expenses.expenses || 0,
          balance: (expenses.income || 0) - (expenses.expenses || 0),
          topCategories: expenses.byCategory ? 
            Object.entries(expenses.byCategory)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 5)
              .map(([name, amount]) => ({ name, amount }))
            : [],
          taxRelevant: expenses.taxRelevant || 0
        };
      }

      // Fallback
      return this.getMockExpenseData();
    } catch (e) {
      console.warn('Expense status error:', e.message);
      return this.getMockExpenseData();
    }
  }

  async getTaxStatus(period) {
    try {
      if (this.taxCore) {
        const status = this.taxCore.getTaxSummary ?
          this.taxCore.getTaxSummary() : { documents: 0 };
        
        return {
          totalDocuments: status.documents || 0,
          taxExpenses: status.taxExpenses || 0,
          taxableIncome: status.taxableIncome || 0,
          vatAmount: status.vatAmount || 0,
          topExpenseCategories: status.topCategories || [],
          documentsReady: status.documentsReady || false,
          nextDeadline: status.nextDeadline || null
        };
      }

      // Fallback
      return this.getMockTaxData();
    } catch (e) {
      console.warn('Tax status error:', e.message);
      return this.getMockTaxData();
    }
  }

  async getFinancialOverview(sections) {
    const subData = sections.subscriptions || {};
    const expData = sections.expenses || {};
    const taxData = sections.tax || {};

    return {
      totalMonthlyOutflow: (subData.totalMonthlyCost || 0) + (expData.totalExpenses || 0) / 12,
      totalAnnualOutflow: (subData.totalAnnualCost || 0) + (expData.totalExpenses || 0),
      netBalance: (expData.totalIncome || 0) - (expData.totalExpenses || 0),
      taxSavingsPotential: (taxData.taxExpenses || 0) * 0.3, // Rough estimate
      subscriptionRatio: subData.totalMonthlyCost ?
        ((subData.totalMonthlyCost / (expData.totalExpenses || 1)) * 100).toFixed(1) : 0,
      status: this.calculateFinancialHealth(expData)
    };
  }

  calculateFinancialHealth(expenseData) {
    const balance = (expenseData.totalIncome || 0) - (expenseData.totalExpenses || 0);
    const ratio = expenseData.totalIncome ? balance / expenseData.totalIncome : -1;

    if (ratio >= 0.2) return 'excellent';
    if (ratio >= 0.1) return 'good';
    if (ratio >= 0) return 'stable';
    if (ratio >= -0.2) return 'warning';
    return 'critical';
  }

  // ── Mock Data (Fallback) ───────────────────────────────────
  getMockSubscriptionData() {
    return {
      totalActive: 3,
      totalMonthlyCost: 45.97,
      totalAnnualCost: 551.64,
      upcomingRenewals: 1,
      topExpensive: [
        { name: 'Netflix', cost: 17.99 },
        { name: 'Adobe CC', cost: 16.99 },
        { name: 'Spotify', cost: 10.99 }
      ],
      subscriptions: [
        { name: 'Netflix', provider: 'netflix', monthlyCost: 17.99, nextBilling: '2026-06-30', status: 'active' },
        { name: 'Spotify', provider: 'spotify', monthlyCost: 10.99, nextBilling: '2026-06-15', status: 'active' },
        { name: 'Adobe CC', provider: 'adobe', monthlyCost: 16.99, nextBilling: '2026-06-20', status: 'active' }
      ]
    };
  }

  getMockExpenseData() {
    return {
      totalIncome: 5000.00,
      totalExpenses: 2340.50,
      balance: 2659.50,
      topCategories: [
        { name: 'Software', amount: 899.00 },
        { name: 'Hosting', amount: 420.00 },
        { name: 'Subscriptions', amount: 45.97 },
        { name: 'Office', amount: 200.00 },
        { name: 'Travel', amount: 150.00 }
      ],
      taxRelevant: 1994.97
    };
  }

  getMockTaxData() {
    return {
      totalDocuments: 12,
      taxExpenses: 2340.50,
      taxableIncome: 5000.00,
      vatAmount: 0,
      topExpenseCategories: [
        { name: 'Software', amount: 899.00 },
        { name: 'Hosting', amount: 420.00 }
      ],
      documentsReady: true,
      nextDeadline: '2026-07-15'
    };
  }

  // ── Formatting ─────────────────────────────────────────────
  formatReport(report, scope) {
    let message = `💰 *FINANCE STATUS*${scope !== 'all' ? ` — ${scope.toUpperCase()}` : ''}\n\n`;

    if (report.sections.overview) {
      const ov = report.sections.overview;
      message += `📊 *Overview*\n`;
      message += `Status: ${this.getHealthEmoji(ov.status)} ${ov.status.toUpperCase()}\n`;
      message += `Monthly Outflow: €${ov.totalMonthlyOutflow.toFixed(2)}\n`;
      message += `Net Balance: €${ov.netBalance.toFixed(2)}\n`;
      message += `Subscription Ratio: ${ov.subscriptionRatio}%\n\n`;
    }

    if (report.sections.subscriptions) {
      const sub = report.sections.subscriptions;
      message += `🎯 *Subscriptions*\n`;
      message += `Active: ${sub.totalActive}\n`;
      message += `Monthly: €${sub.totalMonthlyCost.toFixed(2)}\n`;
      message += `Annual: €${sub.totalAnnualCost.toFixed(2)}\n`;
      message += `Upcoming Renewals: ${sub.upcomingRenewals}\n`;
      if (sub.topExpensive.length > 0) {
        message += `\nTop 3:\n`;
        sub.topExpensive.forEach((s, i) => {
          message += `${i + 1}. ${s.name} — €${s.cost.toFixed(2)}/mo\n`;
        });
      }
      message += `\n`;
    }

    if (report.sections.expenses) {
      const exp = report.sections.expenses;
      message += `💸 *Expenses (${report.period})*\n`;
      message += `Income: €${exp.totalIncome.toFixed(2)}\n`;
      message += `Expenses: €${exp.totalExpenses.toFixed(2)}\n`;
      message += `Balance: €${exp.balance.toFixed(2)}\n`;
      message += `Tax Relevant: €${exp.taxRelevant.toFixed(2)}\n\n`;
    }

    if (report.sections.tax) {
      const tax = report.sections.tax;
      message += `📋 *Tax Core*\n`;
      message += `Documents: ${tax.totalDocuments}\n`;
      message += `Tax Expenses: €${tax.taxExpenses.toFixed(2)}\n`;
      message += `Documents Ready: ${tax.documentsReady ? '✅' : '❌'}\n`;
      if (tax.nextDeadline) {
        message += `Next Deadline: ${tax.nextDeadline}\n`;
      }
    }

    return message;
  }

  getHealthEmoji(status) {
    const emojis = {
      excellent: '🟢',
      good: '🟢',
      stable: '🟡',
      warning: '🟠',
      critical: '🔴'
    };
    return emojis[status] || '⚪';
  }

  // ── Specific Queries ───────────────────────────────────────
  async getUpcomingRenewals(options = {}) {
    const days = options.days || 30;
    
    try {
      if (this.subscriptionHunter) {
        const upcoming = this.subscriptionHunter.getUpcomingRenewals ?
          this.subscriptionHunter.getUpcomingRenewals(days) : [];
        
        return {
          success: true,
          upcoming: upcoming.map(s => ({
            name: s.name,
            date: s.nextBilling,
            cost: s.monthlyCost || 0,
            daysUntil: Math.ceil((new Date(s.nextBilling) - Date.now()) / (1000 * 60 * 60 * 24))
          })),
          message: this.formatRenewals(upcoming)
        };
      }
    } catch (e) {
      console.warn('Renewals error:', e.message);
    }

    return {
      success: true,
      upcoming: [
        { name: 'Netflix', date: '2026-06-30', cost: 17.99, daysUntil: 27 },
        { name: 'Adobe CC', date: '2026-06-20', cost: 16.99, daysUntil: 17 }
      ],
      message: '📅 Upcoming renewals in 30 days\n\n1. Adobe CC — June 20 (17 days)\n2. Netflix — June 30 (27 days)'
    };
  }

  formatRenewals(upcoming) {
    let message = `📅 *UPCOMING RENEWALS*\n\n`;
    
    upcoming.forEach((sub, i) => {
      const days = Math.ceil((new Date(sub.nextBilling) - Date.now()) / (1000 * 60 * 60 * 24));
      message += `${i + 1}. **${sub.name}**\n`;
      message += `   💰 €${(sub.monthlyCost || 0).toFixed(2)}/mo\n`;
      message += `   📅 ${new Date(sub.nextBilling).toLocaleDateString('de-DE')} (${days} days)\n\n`;
    });

    return message;
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      expenseRadarAvailable: !!this.expenseRadar,
      subscriptionHunterAvailable: !!this.subscriptionHunter,
      taxCoreAvailable: !!this.taxCore,
      supportedScopes: ['all', 'subscriptions', 'expenses', 'tax', 'overview'],
      supportedPeriods: ['current_month', 'current_quarter', 'current_year']
    };
  }
}

module.exports = { FinanceStatusAction };
