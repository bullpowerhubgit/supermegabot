const fs = require('fs');
const path = require('path');

/**
 * Expense Radar Service — Laufende Kostenübersichten & Analyse
 * 
 * Funktionen:
 * - Alle laufenden Kosten tracken
 * - Trend-Analyse (Monat/Monat)
 * - Kosten-Kategorien visualisieren
 * - Budget-Tracking
 * - Anomalie-Erkennung
 * - Sparpotenziale identifizieren
 */

class ExpenseRadar {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../state/expenses');
    
    this.categories = {
      'subscriptions': {
        name: 'Abonnements',
        color: '#EF4444',
        icon: '🔄',
        description: 'Wiederkehrende Zahlungen, Software, Services'
      },
      'hosting_infrastructure': {
        name: 'Hosting & Infrastruktur',
        color: '#3B82F6',
        icon: '🌐',
        description: 'Server, Domains, Cloud-Services'
      },
      'software_tools': {
        name: 'Software & Tools',
        color: '#8B5CF6',
        icon: '🛠️',
        description: 'Development-Tools, Design-Software, Produktivität'
      },
      'marketing_ads': {
        name: 'Marketing & Werbung',
        color: '#EC4899',
        icon: '📢',
        description: 'Google Ads, Social Media, Marketing-Tools'
      },
      'payment_fees': {
        name: 'Zahlungsgebühren',
        color: '#F59E0B',
        icon: '💳',
        description: 'Stripe, PayPal, Bank-Gebühren'
      },
      'communication': {
        name: 'Kommunikation',
        color: '#10B981',
        icon: '📞',
        description: 'Telefon, E-Mail, Messaging-Services'
      },
      'legal_compliance': {
        name: 'Recht & Compliance',
        color: '#DC2626',
        icon: '⚖️',
        description: 'Rechtliche Services, Versicherungen, Steuern'
      },
      'other': {
        name: 'Sonstiges',
        color: '#6B7280',
        icon: '📦',
        description: 'Alle anderen Ausgaben'
      }
    };
    
    this.expenses = new Map();
    this.monthlyData = new Map();
    this.budgets = new Map();
    this.alerts = [];
    
    this.ensureStorageDir();
    this.loadExpenseData();
    this.startMonthlyTracking();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadExpenseData() {
    try {
      const filePath = path.join(this.storagePath, 'expenses.json');
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        this.expenses = new Map(data.expenses || []);
        this.monthlyData = new Map(data.monthlyData || []);
        this.budgets = new Map(data.budgets || []);
        this.alerts = data.alerts || [];
      }
    } catch (err) {
      this.logger.error?.('expense.load_failed', { error: err.message });
    }
  }

  saveExpenseData() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'expenses.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          expenses: Array.from(this.expenses.entries()),
          monthlyData: Array.from(this.monthlyData.entries()),
          budgets: Array.from(this.budgets.entries()),
          alerts: this.alerts
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('expense.save_failed', { error: err.message });
    }
  }

  /**
   * Neue Ausgabe hinzufügen
   */
  addExpense(expenseData) {
    const id = `exp_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    const category = this.categorizeExpense(expenseData);
    
    const expense = {
      id,
      name: expenseData.name,
      amount: parseFloat(expenseData.amount),
      category: category.key,
      subcategory: expenseData.subcategory || null,
      type: expenseData.type || 'recurring', // recurring, one-time, variable
      billingCycle: expenseData.billingCycle || 'monthly',
      vendor: expenseData.vendor || null,
      description: expenseData.description || '',
      tags: expenseData.tags || [],
      startDate: expenseData.startDate || new Date().toISOString().split('T')[0],
      endDate: expenseData.endDate || null,
      isActive: expenseData.isActive !== false,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      metadata: {
        confidence: category.confidence,
        detectedFrom: expenseData.detectedFrom || 'manual',
        lastPayment: expenseData.lastPayment || null,
        paymentCount: expenseData.paymentCount || 0,
        averageAmount: expenseData.averageAmount || expenseData.amount
      }
    };
    
    this.expenses.set(id, expense);
    this.updateMonthlyData();
    this.checkBudgetAlerts(expense);
    this.saveExpenseData();
    
    this.logger.info?.('expense.added', { 
      id, 
      name: expense.name, 
      amount: expense.amount, 
      category: expense.category 
    });
    
    return expense;
  }

  /**
   * Ausgabe kategorisieren
   */
  categorizeExpense(expense) {
    const { name = '', vendor = '', description = '' } = expense;
    const searchText = `${name} ${vendor} ${description}`.toLowerCase();
    
    let bestMatch = { key: 'other', confidence: 0 };
    
    for (const [key, category] of Object.entries(this.categories)) {
      let score = 0;
      
      // Category-specific keywords
      const keywords = this.getCategoryKeywords(key);
      for (const keyword of keywords) {
        if (searchText.includes(keyword.toLowerCase())) {
          score += 0.3;
        }
      }
      
      // Vendor matching
      const vendors = this.getCategoryVendors(key);
      for (const vendorName of vendors) {
        if (vendor.toLowerCase().includes(vendorName.toLowerCase()) || 
            name.toLowerCase().includes(vendorName.toLowerCase())) {
          score += 0.5;
        }
      }
      
      if (score > bestMatch.confidence) {
        bestMatch = { key, confidence: score };
      }
    }
    
    return bestMatch;
  }

  /**
   * Keywords für Kategorien
   */
  getCategoryKeywords(category) {
    const keywordMap = {
      'subscriptions': ['abo', 'subscription', 'monatlich', 'wiederkehrend', 'service'],
      'hosting_infrastructure': ['hosting', 'server', 'domain', 'dns', 'cloud', 'vps'],
      'software_tools': ['software', 'tool', 'app', 'license', 'adobe', 'microsoft'],
      'marketing_ads': ['ads', 'marketing', 'werbung', 'google', 'facebook', 'campaign'],
      'payment_fees': ['stripe', 'paypal', 'gebühr', 'fee', 'payment'],
      'communication': ['telefon', 'email', 'messaging', 'slack', 'teams'],
      'legal_compliance': ['recht', 'legal', 'steuer', 'versicherung', 'compliance']
    };
    
    return keywordMap[category] || [];
  }

  /**
   * Vendors für Kategorien
   */
  getCategoryVendors(category) {
    const vendorMap = {
      'subscriptions': ['netflix', 'spotify', 'adobe', 'microsoft', 'apple'],
      'hosting_infrastructure': ['ionos', 'hetzner', 'strato', 'aws', 'digitalocean'],
      'software_tools': ['adobe', 'microsoft', 'figma', 'sketch', 'github'],
      'marketing_ads': ['google', 'facebook', 'instagram', 'linkedin'],
      'payment_fees': ['stripe', 'paypal', 'klarna', 'adyen'],
      'communication': ['telekom', 'vodafone', 'gmail', 'microsoft', 'slack'],
      'legal_compliance': ['elster', 'datev', 'huk24', 'allianz']
    };
    
    return vendorMap[category] || [];
  }

  /**
   * Monatliche Daten aktualisieren
   */
  updateMonthlyData() {
    const currentMonth = new Date().toISOString().slice(0, 7); // YYYY-MM
    
    // Calculate current month totals
    const monthlyTotals = {};
    const activeExpenses = Array.from(this.expenses.values())
      .filter(exp => exp.isActive);
    
    for (const expense of activeExpenses) {
      const monthlyAmount = this.normalizeToMonthly(expense);
      if (!monthlyTotals[expense.category]) {
        monthlyTotals[expense.category] = 0;
      }
      monthlyTotals[expense.category] += monthlyAmount;
    }
    
    const monthData = {
      month: currentMonth,
      total: Object.values(monthlyTotals).reduce((sum, amount) => sum + amount, 0),
      categories: monthlyTotals,
      expenseCount: activeExpenses.length,
      updatedAt: new Date().toISOString()
    };
    
    this.monthlyData.set(currentMonth, monthData);
  }

  /**
   * Betrag auf monatlich normalisieren
   */
  normalizeToMonthly(expense) {
    switch (expense.billingCycle) {
      case 'yearly': return expense.amount / 12;
      case 'quarterly': return expense.amount / 3;
      case 'weekly': return expense.amount * 4.33;
      case 'daily': return expense.amount * 30;
      default: return expense.amount;
    }
  }

  /**
   * Budget-Alerts prüfen
   */
  checkBudgetAlerts(expense) {
    const categoryBudget = this.budgets.get(expense.category);
    if (!categoryBudget) return;
    
    const currentMonth = new Date().toISOString().slice(0, 7);
    const monthData = this.monthlyData.get(currentMonth);
    
    if (monthData && monthData.categories[expense.category]) {
      const currentSpending = monthData.categories[expense.category];
      const budgetPercentage = (currentSpending / categoryBudget.amount) * 100;
      
      if (budgetPercentage >= 100) {
        this.addAlert({
          type: 'budget_exceeded',
          category: expense.category,
          currentSpending,
          budgetAmount: categoryBudget.amount,
          percentage: budgetPercentage,
          severity: 'critical',
          message: `Budget für ${this.categories[expense.category].name} überschritten: ${budgetPercentage.toFixed(0)}%`
        });
      } else if (budgetPercentage >= 80) {
        this.addAlert({
          type: 'budget_warning',
          category: expense.category,
          currentSpending,
          budgetAmount: categoryBudget.amount,
          percentage: budgetPercentage,
          severity: 'warning',
          message: `Budget für ${this.categories[expense.category].name} fast erreicht: ${budgetPercentage.toFixed(0)}%`
        });
      }
    }
  }

  /**
   * Alert hinzufügen
   */
  addAlert(alert) {
    const alertWithId = {
      id: `alert_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
      createdAt: new Date().toISOString(),
      acknowledged: false,
      ...alert
    };
    
    this.alerts.push(alertWithId);
    this.logger.warn?.('expense.alert', { type: alert.type, message: alert.message });
  }

  /**
   * Budget setzen
   */
  setBudget(category, amount, period = 'monthly') {
    const budget = {
      category,
      amount: parseFloat(amount),
      period,
      createdAt: new Date().toISOString(),
      active: true
    };
    
    this.budgets.set(category, budget);
    this.saveExpenseData();
    
    this.logger.info?.('expense.budget_set', { category, amount, period });
    return budget;
  }

  /**
   * Trend-Analyse
   */
  getTrendAnalysis(months = 6) {
    const monthlyArray = Array.from(this.monthlyData.values())
      .sort((a, b) => a.month.localeCompare(b.month))
      .slice(-months);
    
    if (monthlyArray.length < 2) {
      return { trend: 'insufficient_data', change: 0, percentage: 0 };
    }
    
    const latest = monthlyArray[monthlyArray.length - 1];
    const previous = monthlyArray[monthlyArray.length - 2];
    
    const change = latest.total - previous.total;
    const percentage = previous.total > 0 ? (change / previous.total) * 100 : 0;
    
    let trend = 'stable';
    if (Math.abs(percentage) > 5) {
      trend = percentage > 0 ? 'increasing' : 'decreasing';
    }
    
    return {
      trend,
      change,
      percentage,
      latestMonth: latest.month,
      previousMonth: previous.month,
      monthlyData: monthlyArray
    };
  }

  /**
   * Anomalie-Erkennung
   */
  detectAnomalies() {
    const anomalies = [];
    const currentMonth = new Date().toISOString().slice(0, 7);
    const monthData = this.monthlyData.get(currentMonth);
    
    if (!monthData) return anomalies;
    
    // Compare with previous months
    const monthlyArray = Array.from(this.monthlyData.values())
      .sort((a, b) => a.month.localeCompare(b.month));
    
    if (monthlyArray.length < 3) return anomalies;
    
    const previousMonths = monthlyArray.slice(-4, -1);
    const avgPrevious = previousMonths.reduce((sum, month) => sum + month.total, 0) / previousMonths.length;
    
    const deviation = Math.abs(monthData.total - avgPrevious);
    const percentageDeviation = avgPrevious > 0 ? (deviation / avgPrevious) * 100 : 0;
    
    if (percentageDeviation > 30) {
      anomalies.push({
        type: 'spending_spike',
        severity: deviation > 0 ? 'warning' : 'info',
        current: monthData.total,
        average: avgPrevious,
        deviation: deviation,
        percentage: percentageDeviation,
        message: `Ausgabenabweichung: ${percentageDeviation.toFixed(0)}% ${deviation > 0 ? 'über' : 'unter'} Durchschnitt`
      });
    }
    
    // Category-specific anomalies
    for (const [category, amount] of Object.entries(monthData.categories)) {
      const categoryAvg = previousMonths.reduce((sum, month) => 
        sum + (month.categories[category] || 0), 0) / previousMonths.length;
      
      const categoryDeviation = Math.abs(amount - categoryAvg);
      const categoryPercentage = categoryAvg > 0 ? (categoryDeviation / categoryAvg) * 100 : 0;
      
      if (categoryPercentage > 50 && amount > 50) {
        anomalies.push({
          type: 'category_anomaly',
          severity: 'warning',
          category,
          current: amount,
          average: categoryAvg,
          deviation: categoryDeviation,
          percentage: categoryPercentage,
          message: `Kategorie ${this.categories[category].name}: ${categoryPercentage.toFixed(0)}% Abweichung`
        });
      }
    }
    
    return anomalies;
  }

  /**
   * Sparpotenziale identifizieren
   */
  identifySavingsOpportunities() {
    const opportunities = [];
    const activeExpenses = Array.from(this.expenses.values())
      .filter(exp => exp.isActive)
      .sort((a, b) => b.amount - a.amount);
    
    // High-value subscriptions
    const highValueSubscriptions = activeExpenses.filter(exp => 
      exp.category === 'subscriptions' && exp.amount > 50
    );
    
    for (const expense of highValueSubscriptions) {
      opportunities.push({
        type: 'downgrade_subscription',
        priority: 'high',
        expense: expense.name,
        currentCost: expense.amount,
        potentialSavings: expense.amount * 0.3, // 30% savings estimate
        description: `Downgrade oder Alternative für ${expense.name} prüfen`
      });
    }
    
    // Unused or low-usage services
    const lowUsageServices = activeExpenses.filter(exp => 
      exp.metadata.paymentCount < 3 && exp.amount > 20
    );
    
    for (const expense of lowUsageServices) {
      opportunities.push({
        type: 'cancel_unused',
        priority: 'medium',
        expense: expense.name,
        currentCost: expense.amount,
        potentialSavings: expense.amount,
        description: `Kaum genutzter Service: ${expense.name}`
      });
    }
    
    // Budget overruns
    const currentMonth = new Date().toISOString().slice(0, 7);
    const monthData = this.monthlyData.get(currentMonth);
    
    if (monthData) {
      for (const [category, spending] of Object.entries(monthData.categories)) {
        const budget = this.budgets.get(category);
        if (budget && spending > budget.amount) {
          opportunities.push({
            type: 'reduce_category_spending',
            priority: 'high',
            category,
            currentSpending: spending,
            budget: budget.amount,
            overspend: spending - budget.amount,
            description: `Ausgaben in ${this.categories[category].name} reduzieren`
          });
        }
      }
    }
    
    return opportunities.sort((a, b) => {
      const priorityOrder = { high: 3, medium: 2, low: 1 };
      return priorityOrder[b.priority] - priorityOrder[a.priority];
    });
  }

  /**
   * Vollständige Übersicht
   */
  getRadarOverview() {
    const currentMonth = new Date().toISOString().slice(0, 7);
    const monthData = this.monthlyData.get(currentMonth);
    const trend = this.getTrendAnalysis();
    const anomalies = this.detectAnomalies();
    const opportunities = this.identifySavingsOpportunities();
    const activeAlerts = this.alerts.filter(alert => !alert.acknowledged);
    
    return {
      generatedAt: new Date().toISOString(),
      currentMonth: {
        month: currentMonth,
        total: monthData?.total || 0,
        categories: monthData?.categories || {},
        expenseCount: monthData?.expenseCount || 0
      },
      trend,
      anomalies,
      opportunities,
      alerts: activeAlerts,
      budgets: Array.from(this.budgets.values()),
      categories: this.categories,
      summary: {
        totalMonthlyExpenses: monthData?.total || 0,
        activeExpenses: this.expenses.size,
        budgetAlerts: activeAlerts.filter(a => a.type.includes('budget')).length,
        anomaliesCount: anomalies.length,
        savingsPotential: opportunities.reduce((sum, opp) => sum + opp.potentialSavings, 0)
      }
    };
  }

  /**
   * Monatliche Historie
   */
  getMonthlyHistory(months = 12) {
    return Array.from(this.monthlyData.values())
      .sort((a, b) => a.month.localeCompare(b.month))
      .slice(-months);
  }

  /**
   * Start monthly tracking
   */
  startMonthlyTracking() {
    // Update monthly data every hour
    setInterval(() => {
      this.updateMonthlyData();
    }, 60 * 60 * 1000);
    
    // Check for alerts every 6 hours
    setInterval(() => {
      const anomalies = this.detectAnomalies();
      if (anomalies.length > 0) {
        this.logger.warn?.('expense.anomalies_detected', { count: anomalies.length });
      }
    }, 6 * 60 * 60 * 1000);
  }
}

module.exports = { ExpenseRadar };
