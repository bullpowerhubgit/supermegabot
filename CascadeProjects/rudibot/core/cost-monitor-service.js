const fs = require('fs');
const path = require('path');

/**
 * Cost Monitor Service — Revenue + Cost Visibility für Dashboard
 * 
 * Tracks:
 * - Einnahmen (heute, 7 Tage, 30 Tage)
 * - Ausgaben (Tools, SaaS, APIs, Abos)
 * - Marge und Gebühren
 * - Unnötige Kosten
 * - Verdächtige Anstiege
 */

class CostMonitorService {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/cost-monitor');
    this.costData = new Map();
    this.revenueData = new Map();
    this.alerts = [];
    
    this.ensureStorageDir();
    this.loadHistoricalData();
    this.initializeCostCategories();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadHistoricalData() {
    // Simulate historical data for demo
    const today = new Date();
    
    // Last 30 days of revenue
    for (let i = 29; i >= 0; i--) {
      const date = new Date(today);
      date.setDate(date.getDate() - i);
      const dateKey = date.toISOString().split('T')[0];
      
      // Simulate daily revenue with some variance
      const baseRevenue = 1200;
      const variance = Math.random() * 400 - 200;
      this.revenueData.set(dateKey, Math.max(800, baseRevenue + variance));
    }
    
    // Cost categories
    this.costData.set('saas_tools', {
      monthly: 450,
      items: [
        { name: 'Shopify', cost: 89, category: 'ecommerce' },
        { name: 'HubSpot', cost: 120, category: 'crm' },
        { name: 'Slack', cost: 8, category: 'communication' },
        { name: 'Notion', cost: 10, category: 'productivity' },
        { name: 'Figma', cost: 15, category: 'design' }
      ]
    });
    
    this.costData.set('apis', {
      monthly: 180,
      items: [
        { name: 'OpenAI API', cost: 85, category: 'ai' },
        { name: 'Anthropic Claude', cost: 65, category: 'ai' },
        { name: 'Stripe Processing', cost: 30, category: 'payments' }
      ]
    });
    
    this.costData.set('infrastructure', {
      monthly: 120,
      items: [
        { name: 'Vercel Pro', cost: 20, category: 'hosting' },
        { name: 'AWS EC2', cost: 75, category: 'servers' },
        { name: 'Cloudflare', cost: 25, category: 'cdn' }
      ]
    });
    
    this.costData.set('marketing', {
      monthly: 280,
      items: [
        { name: 'Google Ads', cost: 150, category: 'advertising' },
        { name: 'Facebook Ads', cost: 130, category: 'advertising' }
      ]
    });
  }

  initializeCostCategories() {
    this.categories = {
      'saas_tools': { name: 'SaaS Tools', color: '#3B82F6', priority: 1 },
      'apis': { name: 'APIs', color: '#10B981', priority: 2 },
      'infrastructure': { name: 'Infrastruktur', color: '#F59E0B', priority: 3 },
      'marketing': { name: 'Marketing', color: '#EF4444', priority: 4 }
    };
  }

  /**
   * Revenue Summary
   */
  getRevenueSummary() {
    const today = new Date().toISOString().split('T')[0];
    const todayRevenue = this.revenueData.get(today) || 0;
    
    // Last 7 days
    const last7Days = [];
    let total7Days = 0;
    for (let i = 6; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      const dateKey = date.toISOString().split('T')[0];
      const revenue = this.revenueData.get(dateKey) || 0;
      last7Days.push({ date: dateKey, revenue });
      total7Days += revenue;
    }
    
    // Last 30 days
    const last30Days = [];
    let total30Days = 0;
    for (let i = 29; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      const dateKey = date.toISOString().split('T')[0];
      const revenue = this.revenueData.get(dateKey) || 0;
      last30Days.push({ date: dateKey, revenue });
      total30Days += revenue;
    }
    
    // Calculate growth
    const previous7Days = last7Days.slice(0, 7).reduce((sum, day) => sum + day.revenue, 0);
    const growth7Days = total7Days > 0 ? ((total7Days - previous7Days) / previous7Days * 100).toFixed(1) : 0;
    
    return {
      today: todayRevenue,
      last7Days: {
        total: total7Days,
        average: (total7Days / 7).toFixed(0),
        growth: parseFloat(growth7Days),
        daily: last7Days
      },
      last30Days: {
        total: total30Days,
        average: (total30Days / 30).toFixed(0),
        daily: last30Days
      },
      trends: {
        direction: growth7Days > 0 ? 'up' : 'down',
        momentum: Math.abs(growth7Days)
      }
    };
  }

  /**
   * Cost Summary
   */
  getCostSummary() {
    const totalCosts = {};
    let grandTotal = 0;
    
    for (const [category, data] of this.costData) {
      totalCosts[category] = data.monthly;
      grandTotal += data.monthly;
    }
    
    // Calculate cost breakdown
    const breakdown = [];
    for (const [category, total] of Object.entries(totalCosts)) {
      const percentage = grandTotal > 0 ? (total / grandTotal * 100).toFixed(1) : 0;
      breakdown.push({
        category,
        name: this.categories[category]?.name || category,
        total,
        percentage: parseFloat(percentage),
        color: this.categories[category]?.color || '#6B7280',
        items: this.costData.get(category)?.items || []
      });
    }
    
    // Sort by total cost
    breakdown.sort((a, b) => b.total - a.total);
    
    return {
      grandTotal,
      breakdown,
      monthlyTrend: this.calculateCostTrend(),
      alerts: this.getCostAlerts()
    };
  }

  /**
   * Calculate cost trends
   */
  calculateCostTrend() {
    // Simulate cost trend data
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
    const trend = [];
    
    for (let i = 0; i < months.length; i++) {
      const baseCost = 1030; // Current monthly total
      const variance = Math.random() * 100 - 50;
      trend.push({
        month: months[i],
        cost: Math.max(900, baseCost + variance)
      });
    }
    
    // Calculate trend direction
    const recent = trend.slice(-2);
    const trendDirection = recent[1].cost > recent[0].cost ? 'up' : 'down';
    const trendPercent = ((recent[1].cost - recent[0].cost) / recent[0].cost * 100).toFixed(1);
    
    return {
      monthly: trend,
      direction: trendDirection,
      change: parseFloat(trendPercent)
    };
  }

  /**
   * Get cost alerts and warnings
   */
  getCostAlerts() {
    const alerts = [];
    
    // Check for unusual cost increases
    for (const [category, data] of this.costData) {
      for (const item of data.items) {
        // Simulate unusual cost detection
        if (item.cost > 100 && Math.random() > 0.7) {
          alerts.push({
            type: 'warning',
            category: 'cost_increase',
            message: `${item.name} Kosten ungewöhnlich hoch (${item.cost}€)`,
            item: item.name,
            category_name: this.categories[category]?.name || category,
            recommendation: 'Nutzung prüfen oder Plan anpassen'
          });
        }
        
        // Check for unused tools
        if (Math.random() > 0.8) {
          alerts.push({
            type: 'info',
            category: 'unused_tool',
            message: `${item.name} scheint ungenutzt`,
            item: item.name,
            category_name: this.categories[category]?.name || category,
            recommendation: 'Tool deaktivieren oder kündigen'
          });
        }
      }
    }
    
    return alerts;
  }

  /**
   * Business Health Score
   */
  getBusinessHealth() {
    const revenue = this.getRevenueSummary();
    const costs = this.getCostSummary();
    
    // Calculate metrics
    const monthlyRevenue = revenue.last30Days.average;
    const monthlyCosts = costs.grandTotal;
    const monthlyProfit = monthlyRevenue - monthlyCosts;
    const profitMargin = monthlyRevenue > 0 ? (monthlyProfit / monthlyRevenue * 100).toFixed(1) : 0;
    
    // Health scoring
    let healthScore = 100;
    
    // Profit margin impact
    if (parseFloat(profitMargin) < 10) healthScore -= 20;
    else if (parseFloat(profitMargin) < 20) healthScore -= 10;
    
    // Revenue trend impact
    if (revenue.trends.direction === 'down' && revenue.trends.momentum > 10) healthScore -= 15;
    else if (revenue.trends.direction === 'up' && revenue.trends.momentum > 10) healthScore += 5;
    
    // Cost alerts impact
    const costAlerts = costs.alerts.filter(a => a.type === 'warning').length;
    healthScore -= costAlerts * 5;
    
    // Determine status
    let status = 'excellent';
    if (healthScore < 60) status = 'critical';
    else if (healthScore < 75) status = 'warning';
    else if (healthScore < 90) status = 'good';
    
    return {
      score: Math.max(0, Math.min(100, healthScore)),
      status,
      metrics: {
        monthlyRevenue,
        monthlyCosts,
        monthlyProfit,
        profitMargin: parseFloat(profitMargin),
        revenueGrowth: revenue.last7Days.growth,
        costTrend: costs.monthlyTrend.direction
      },
      alerts: costs.alerts,
      recommendations: this.getRecommendations(healthScore, profitMargin, costAlerts)
    };
  }

  /**
   * Get business recommendations
   */
  getRecommendations(healthScore, profitMargin, costAlerts) {
    const recommendations = [];
    
    if (parseFloat(profitMargin) < 15) {
      recommendations.push({
        priority: 'high',
        type: 'profit',
        message: 'Profit-Marge unter 15% - Kosten optimieren',
        action: 'Kostenanalyse und Reduzierung nicht-essentieller Tools'
      });
    }
    
    if (costAlerts > 2) {
      recommendations.push({
        priority: 'medium',
        type: 'cost_management',
        message: 'Mehrere Kosten-Warnungen aktiv',
        action: 'Kosten-Überprüfung und Tool-Rationalisierung'
      });
    }
    
    if (healthScore < 75) {
      recommendations.push({
        priority: 'high',
        type: 'health',
        message: 'Business-Health Score niedrig',
        action: 'Umfassende Business-Analyse durchführen'
      });
    }
    
    // Always include optimization suggestions
    recommendations.push({
      priority: 'low',
      type: 'optimization',
      message: 'Automatisierungspotenziale prüfen',
      action: 'Wiederkehrende Aufgaben identifizieren und automatisieren'
    });
    
    return recommendations;
  }

  /**
   * Add revenue entry
   */
  addRevenue(date, amount, source = 'unknown') {
    const dateKey = date instanceof Date ? date.toISOString().split('T')[0] : date;
    const current = this.revenueData.get(dateKey) || 0;
    this.revenueData.set(dateKey, current + amount);
    
    this.logger.info?.('cost-monitor.revenue.added', {
      date: dateKey,
      amount,
      source,
      total: current + amount
    });
  }

  /**
   * Add cost entry
   */
  addCost(category, item, amount, details = {}) {
    if (!this.costData.has(category)) {
      this.costData.set(category, {
        monthly: 0,
        items: []
      });
    }
    
    const categoryData = this.costData.get(category);
    const existingItem = categoryData.items.find(i => i.name === item);
    
    if (existingItem) {
      existingItem.cost = amount;
      existingItem.details = details;
    } else {
      categoryData.items.push({
        name: item,
        cost: amount,
        category: details.category || 'other',
        details
      });
    }
    
    // Recalculate monthly total
    categoryData.monthly = categoryData.items.reduce((sum, i) => sum + i.cost, 0);
    
    this.logger.info?.('cost-monitor.cost.added', {
      category,
      item,
      amount,
      monthlyTotal: categoryData.monthly
    });
  }

  /**
   * Get dashboard data
   */
  getDashboardData() {
    return {
      revenue: this.getRevenueSummary(),
      costs: this.getCostSummary(),
      health: this.getBusinessHealth(),
      alerts: this.getCostAlerts(),
      lastUpdated: new Date().toISOString()
    };
  }
}

module.exports = { CostMonitorService };
