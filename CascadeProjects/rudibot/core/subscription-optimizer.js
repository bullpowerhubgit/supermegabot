const fs = require('fs');
const path = require('path');

/**
 * Subscription Optimizer — Automatische Kostenminimierung
 * 
 * Funktionen:
 * - Trackt alle Abos, Verträge, Apps, Plattformen
 * - Analysiert Nutzung und identifiziert unnötige Ausgaben
 * - Generiert Kündigungsempfehlungen
 * - Bereitet automatische Kündigungen vor (mit Approval)
 * - Sendet Erinnerungen für Kündigungstermine
 * - Identifiziert nicht genutzte Plattformen
 */

class SubscriptionOptimizer {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.orchestrator = options.orchestrator;
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/subscriptions');
    this.subscriptions = new Map();
    this.cancellationQueue = [];
    this.reminders = [];
    
    this.ensureStorageDir();
    this.loadSubscriptions();
    this.initializeDefaultSubscriptions();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadSubscriptions() {
    try {
      const filePath = path.join(this.storagePath, 'subscriptions.json');
      if (fs.existsSync(filePath)) {
        const content = fs.readFileSync(filePath, 'utf8');
        const data = JSON.parse(content);
        for (const sub of data.subscriptions || []) {
          this.subscriptions.set(sub.id, sub);
        }
      }
    } catch (err) {
      this.logger.error?.('optimizer.load_failed', { error: err.message });
    }
  }

  saveSubscriptions() {
    try {
      const filePath = path.join(this.storagePath, 'subscriptions.json');
      const data = {
        updatedAt: new Date().toISOString(),
        subscriptions: Array.from(this.subscriptions.values())
      };
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
    } catch (err) {
      this.logger.error?.('optimizer.save_failed', { error: err.message });
    }
  }

  initializeDefaultSubscriptions() {
    // Demo subscriptions - in production these come from user input
    const defaults = [
      {
        id: 'sub_shopify',
        name: 'Shopify Basic',
        category: 'ecommerce',
        cost: 29,
        currency: 'EUR',
        billingCycle: 'monthly',
        nextBilling: '2026-06-15',
        cancelDeadline: '2026-06-08',
        usage: { lastUsed: '2026-06-01', frequency: 'daily', score: 95 },
        platform: 'SaaS',
        url: 'https://admin.shopify.com',
        autoRenew: true,
        status: 'active'
      },
      {
        id: 'sub_hubspot',
        name: 'HubSpot Marketing',
        category: 'crm',
        cost: 120,
        currency: 'EUR',
        billingCycle: 'monthly',
        nextBilling: '2026-06-20',
        cancelDeadline: '2026-06-13',
        usage: { lastUsed: '2026-05-15', frequency: 'weekly', score: 30 },
        platform: 'SaaS',
        url: 'https://app.hubspot.com',
        autoRenew: true,
        status: 'active'
      },
      {
        id: 'sub_adobe',
        name: 'Adobe Creative Cloud',
        category: 'design',
        cost: 60,
        currency: 'EUR',
        billingCycle: 'monthly',
        nextBilling: '2026-06-25',
        cancelDeadline: '2026-06-18',
        usage: { lastUsed: '2026-03-10', frequency: 'none', score: 5 },
        platform: 'SaaS',
        url: 'https://creativecloud.adobe.com',
        autoRenew: true,
        status: 'active'
      },
      {
        id: 'sub_zoom',
        name: 'Zoom Pro',
        category: 'communication',
        cost: 14,
        currency: 'EUR',
        billingCycle: 'monthly',
        nextBilling: '2026-06-10',
        cancelDeadline: '2026-06-03',
        usage: { lastUsed: '2026-06-02', frequency: 'daily', score: 90 },
        platform: 'SaaS',
        url: 'https://zoom.us',
        autoRenew: true,
        status: 'active'
      },
      {
        id: 'sub_notion',
        name: 'Notion Team',
        category: 'productivity',
        cost: 10,
        currency: 'EUR',
        billingCycle: 'monthly',
        nextBilling: '2026-06-12',
        cancelDeadline: '2026-06-05',
        usage: { lastUsed: '2026-05-20', frequency: 'weekly', score: 40 },
        platform: 'SaaS',
        url: 'https://notion.so',
        autoRenew: true,
        status: 'active'
      },
      {
        id: 'sub_aws',
        name: 'AWS EC2 + S3',
        category: 'infrastructure',
        cost: 75,
        currency: 'EUR',
        billingCycle: 'monthly',
        nextBilling: '2026-06-30',
        cancelDeadline: '2026-06-23',
        usage: { lastUsed: '2026-06-03', frequency: 'continuous', score: 100 },
        platform: 'Cloud',
        url: 'https://aws.amazon.com',
        autoRenew: true,
        status: 'active'
      }
    ];

    for (const sub of defaults) {
      if (!this.subscriptions.has(sub.id)) {
        this.subscriptions.set(sub.id, sub);
      }
    }
    
    this.saveSubscriptions();
  }

  /**
   * Analyze all subscriptions and generate recommendations
   */
  analyze() {
    const today = new Date();
    const recommendations = {
      immediateCancel: [],
      considerCancel: [],
      optimizePlan: [],
      keep: [],
      totalMonthlyCost: 0,
      potentialSavings: 0,
      unusedPlatforms: []
    };

    for (const [id, sub] of this.subscriptions) {
      if (sub.status !== 'active') continue;

      recommendations.totalMonthlyCost += sub.cost;
      const daysSinceUse = this.daysSince(sub.usage.lastUsed);
      const usageScore = sub.usage.score;

      // Unused for 60+ days → immediate cancel
      if (daysSinceUse > 60 || usageScore < 20) {
        recommendations.immediateCancel.push({
          id,
          name: sub.name,
          cost: sub.cost,
          reason: `Nicht genutzt seit ${daysSinceUse} Tagen (Score: ${usageScore}%)`,
          saving: sub.cost,
          deadline: sub.cancelDeadline,
          risk: 'low'
        });
        recommendations.potentialSavings += sub.cost;
      }
      // Low usage → consider cancel
      else if (daysSinceUse > 30 || usageScore < 50) {
        recommendations.considerCancel.push({
          id,
          name: sub.name,
          cost: sub.cost,
          reason: `Wenig genutzt: ${daysSinceUse} Tage her, Score ${usageScore}%`,
          saving: sub.cost,
          deadline: sub.cancelDeadline,
          risk: 'medium'
        });
        recommendations.potentialSavings += sub.cost;
      }
      // Medium usage → optimize plan
      else if (usageScore < 80) {
        recommendations.optimizePlan.push({
          id,
          name: sub.name,
          cost: sub.cost,
          reason: `Mäßige Nutzung: ${usageScore}% — prüfe kleineren Plan`,
          saving: sub.cost * 0.3, // Estimated 30% savings
          deadline: sub.cancelDeadline,
          risk: 'low'
        });
        recommendations.potentialSavings += sub.cost * 0.3;
      }
      // High usage → keep
      else {
        recommendations.keep.push({
          id,
          name: sub.name,
          cost: sub.cost,
          reason: `Aktiv genutzt: ${usageScore}%`,
          risk: 'none'
        });
      }

      // Check for upcoming deadlines
      const daysUntilDeadline = this.daysUntil(sub.cancelDeadline);
      if (daysUntilDeadline <= 7 && daysUntilDeadline >= 0) {
        this.reminders.push({
          id: `${id}_reminder`,
          subscriptionId: id,
          type: 'cancellation_deadline',
          deadline: sub.cancelDeadline,
          daysLeft: daysUntilDeadline,
          name: sub.name,
          cost: sub.cost
        });
      }
    }

    // Find unused platforms
    recommendations.unusedPlatforms = this.findUnusedPlatforms();

    return recommendations;
  }

  /**
   * Find platforms that haven't been used in 90+ days
   */
  findUnusedPlatforms() {
    const unused = [];
    for (const [id, sub] of this.subscriptions) {
      if (sub.status !== 'active') continue;
      const daysSinceUse = this.daysSince(sub.usage.lastUsed);
      if (daysSinceUse > 90) {
        unused.push({
          id,
          name: sub.name,
          platform: sub.platform,
          daysUnused: daysSinceUse,
          monthlyCost: sub.cost,
          url: sub.url
        });
      }
    }
    return unused;
  }

  /**
   * Prepare cancellation for a subscription
   */
  async prepareCancellation(subscriptionId, reason = '') {
    const sub = this.subscriptions.get(subscriptionId);
    if (!sub) {
      throw new Error(`Subscription ${subscriptionId} not found`);
    }

    const cancellation = {
      id: `cancel_${Date.now()}`,
      subscriptionId,
      name: sub.name,
      cost: sub.cost,
      reason: reason || 'Automatisch: Wenig/Nicht genutzt',
      preparedAt: new Date().toISOString(),
      status: 'prepared',
      riskLevel: sub.cost > 50 ? 'yellow' : 'green',
      cancellationUrl: sub.url,
      deadline: sub.cancelDeadline,
      estimatedSaving: sub.cost
    };

    this.cancellationQueue.push(cancellation);
    this.logger.info?.('optimizer.cancellation.prepared', {
      cancellationId: cancellation.id,
      subscription: sub.name,
      saving: sub.cost
    });

    // If orchestrator available, submit for approval/execution
    if (this.orchestrator) {
      try {
        const result = await this.orchestrator.submitCommand({
          action: 'cancel_subscription',
          target: subscriptionId,
          details: cancellation,
          source: 'optimizer'
        }, 'optimizer');
        cancellation.jobId = result.jobId;
      } catch (err) {
        this.logger.warn?.('optimizer.cancellation.orchestrator_failed', { error: err.message });
      }
    }

    return cancellation;
  }

  /**
   * Execute all recommended cancellations (requires approval for expensive ones)
   */
  async executeRecommendedCancellations() {
    const analysis = this.analyze();
    const results = [];

    // Immediate cancellations
    for (const rec of analysis.immediateCancel) {
      try {
        const result = await this.prepareCancellation(rec.id, rec.reason);
        results.push({
          subscription: rec.name,
          status: 'prepared',
          saving: rec.saving,
          requiresApproval: rec.cost > 50
        });
      } catch (err) {
        results.push({
          subscription: rec.name,
          status: 'failed',
          error: err.message
        });
      }
    }

    return {
      executed: results.length,
      results,
      totalPotentialSavings: analysis.potentialSavings
    };
  }

  /**
   * Get all reminders for upcoming deadlines
   */
  getReminders() {
    const today = new Date();
    const activeReminders = this.reminders.filter(r => {
      const deadline = new Date(r.deadline);
      return deadline >= today;
    });

    return activeReminders.sort((a, b) => 
      new Date(a.deadline) - new Date(b.deadline)
    );
  }

  /**
   * Get optimization report
   */
  getReport() {
    const analysis = this.analyze();
    const reminders = this.getReminders();
    const totalActive = Array.from(this.subscriptions.values()).filter(s => s.status === 'active').length;

    return {
      generatedAt: new Date().toISOString(),
      summary: {
        totalSubscriptions: totalActive,
        totalMonthlyCost: analysis.totalMonthlyCost,
        potentialMonthlySavings: analysis.potentialSavings,
        immediateCancellations: analysis.immediateCancel.length,
        considerCancellations: analysis.considerCancel.length,
        optimizePlans: analysis.optimizePlan.length,
        upcomingDeadlines: reminders.length
      },
      recommendations: {
        immediateCancel: analysis.immediateCancel,
        considerCancel: analysis.considerCancel,
        optimizePlan: analysis.optimizePlan,
        keep: analysis.keep
      },
      unusedPlatforms: analysis.unusedPlatforms,
      reminders,
      cancellationQueue: this.cancellationQueue
    };
  }

  /**
   * Add or update a subscription
   */
  addSubscription(subscriptionData) {
    const id = subscriptionData.id || `sub_${Date.now()}`;
    const sub = {
      id,
      ...subscriptionData,
      addedAt: new Date().toISOString(),
      status: 'active'
    };
    
    this.subscriptions.set(id, sub);
    this.saveSubscriptions();
    
    this.logger.info?.('optimizer.subscription.added', { id, name: sub.name });
    return sub;
  }

  /**
   * Update subscription usage
   */
  updateUsage(subscriptionId, usageData) {
    const sub = this.subscriptions.get(subscriptionId);
    if (!sub) {
      throw new Error(`Subscription ${subscriptionId} not found`);
    }

    sub.usage = { ...sub.usage, ...usageData, lastUpdated: new Date().toISOString() };
    this.subscriptions.set(subscriptionId, sub);
    this.saveSubscriptions();
    
    return sub;
  }

  /**
   * Mark subscription as cancelled
   */
  markCancelled(subscriptionId, details = {}) {
    const sub = this.subscriptions.get(subscriptionId);
    if (!sub) {
      throw new Error(`Subscription ${subscriptionId} not found`);
    }

    sub.status = 'cancelled';
    sub.cancelledAt = new Date().toISOString();
    sub.cancellationDetails = details;
    this.subscriptions.set(subscriptionId, sub);
    this.saveSubscriptions();
    
    this.logger.info?.('optimizer.subscription.cancelled', { id: subscriptionId, name: sub.name });
    return sub;
  }

  /**
   * Utility: Days since date
   */
  daysSince(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    return Math.floor((now - date) / (1000 * 60 * 60 * 24));
  }

  /**
   * Utility: Days until date
   */
  daysUntil(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    return Math.floor((date - now) / (1000 * 60 * 60 * 24));
  }
}

module.exports = { SubscriptionOptimizer };
