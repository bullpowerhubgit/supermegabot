const fs = require('fs');
const path = require('path');

/**
 * Subscription Classifier — Intelligente Abo-Klassifizierung
 * 
 * Kombiniert Daten aus:
 * - PayPal Import
 * - Bank Import  
 * - Manuelle Eingabe
 * - API-Abfragen
 * 
 * Erstellt ein einheitliches Abo-Profil mit:
 * - Kategorisierung
 * - Nutzungs-Score
 * - Kündigungsempfehlung
 * - Priorisierung
 */

class SubscriptionClassifier {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../state/classified');
    this.subscriptions = new Map();
    this.categories = new Map();
    
    this.initializeCategories();
    this.loadClassified();
  }

  initializeCategories() {
    const defaultCategories = {
      'essential': { priority: 1, color: '#10B981', keepThreshold: 80 },
      'productivity': { priority: 2, color: '#3B82F6', keepThreshold: 60 },
      'communication': { priority: 2, color: '#6366F1', keepThreshold: 60 },
      'development': { priority: 2, color: '#8B5CF6', keepThreshold: 60 },
      'ecommerce': { priority: 3, color: '#F59E0B', keepThreshold: 70 },
      'marketing': { priority: 3, color: '#EC4899', keepThreshold: 50 },
      'design': { priority: 3, color: '#14B8A6', keepThreshold: 40 },
      'storage': { priority: 4, color: '#6B7280', keepThreshold: 50 },
      'entertainment': { priority: 5, color: '#EF4444', keepThreshold: 30 },
      'other': { priority: 5, color: '#9CA3AF', keepThreshold: 40 }
    };
    
    for (const [key, value] of Object.entries(defaultCategories)) {
      this.categories.set(key, value);
    }
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadClassified() {
    try {
      const filePath = path.join(this.storagePath, 'classified.json');
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        for (const sub of data.subscriptions || []) {
          this.subscriptions.set(sub.id, sub);
        }
      }
    } catch (err) {
      this.logger.error?.('classifier.load_failed', { error: err.message });
    }
  }

  saveClassified() {
    try {
      this.ensureStorageDir();
      fs.writeFileSync(
        path.join(this.storagePath, 'classified.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          subscriptions: Array.from(this.subscriptions.values())
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('classifier.save_failed', { error: err.message });
    }
  }

  /**
   * Merge subscriptions from multiple sources
   */
  mergeFromSources(sources) {
    const merged = new Map();
    
    for (const source of sources) {
      for (const sub of source.subscriptions || []) {
        const existing = merged.get(sub.id);
        
        if (existing) {
          // Merge data from multiple sources
          existing.sources = [...(existing.sources || []), sub.source];
          existing.paymentCount = Math.max(existing.paymentCount || 0, sub.paymentCount || 0);
          existing.confidence = Math.min((existing.confidence || 0.5) + 0.2, 1.0);
          
          // Use most recent data
          if (new Date(sub.lastPayment) > new Date(existing.lastPayment)) {
            existing.lastPayment = sub.lastPayment;
            existing.cost = sub.cost;
          }
        } else {
          merged.set(sub.id, {
            ...sub,
            sources: [sub.source],
            confidence: 0.5,
            classifiedAt: new Date().toISOString()
          });
        }
      }
    }
    
    this.subscriptions = merged;
    this.classifyAll();
    this.saveClassified();
    
    return Array.from(merged.values());
  }

  /**
   * Classify all subscriptions with usage scores and recommendations
   */
  classifyAll() {
    for (const [id, sub] of this.subscriptions) {
      const category = this.categories.get(sub.category) || this.categories.get('other');
      
      // Calculate usage score based on multiple factors
      const usageScore = this.calculateUsageScore(sub);
      
      // Determine action
      let action = 'keep';
      let actionReason = 'Aktiv genutzt';
      let priority = 'low';
      let isProtected = sub.protected || false;
      
      // Check if manually marked as protected
      if (isProtected) {
        action = 'protected';
        actionReason = `Geschützt: ${sub.protectedReason || 'Manuell geschützt'}`;
        priority = 'none';
      } else if (usageScore < 20) {
        action = 'cancel_immediately';
        actionReason = `Nicht genutzt (Score: ${usageScore}%) — Sofort kündigen`;
        priority = 'high';
      } else if (usageScore < category.keepThreshold) {
        action = 'review';
        actionReason = `Wenig genutzt (Score: ${usageScore}%, Threshold: ${category.keepThreshold}%)`;
        priority = 'medium';
      } else if (usageScore < 80) {
        action = 'downgrade';
        actionReason = `Mäßige Nutzung (Score: ${usageScore}%) — Prüfe kleineren Plan`;
        priority = 'low';
      }
      
      // Calculate financial impact
      const monthlyCost = this.normalizeMonthlyCost(sub);
      const yearlyCost = monthlyCost * 12;
      
      this.subscriptions.set(id, {
        ...sub,
        classification: {
          category: sub.category || 'other',
          categoryPriority: category.priority,
          categoryColor: category.color,
          usageScore,
          action,
          actionReason,
          priority,
          monthlyCost,
          yearlyCost,
          confidence: sub.confidence || 0.5
        }
      });
    }
  }

  /**
   * Calculate usage score from multiple signals
   */
  calculateUsageScore(sub) {
    let score = 50; // Base score
    
    // Factor 1: Days since last payment/use
    const daysSince = this.daysSince(sub.lastPayment);
    if (daysSince > 90) score -= 40;
    else if (daysSince > 60) score -= 30;
    else if (daysSince > 30) score -= 15;
    else score += 10;
    
    // Factor 2: Payment frequency consistency
    if (sub.paymentCount >= 12) score += 10;
    else if (sub.paymentCount >= 6) score += 5;
    else if (sub.paymentCount < 3) score -= 10;
    
    // Factor 3: Manual usage tracking (if available)
    if (sub.manualUsage) {
      score = (score + sub.manualUsage) / 2;
    }
    
    // Factor 4: Category-specific adjustments
    const categoryAdjustments = {
      'essential': 20,
      'ecommerce': 15,
      'development': 10,
      'productivity': 5,
      'communication': 5,
      'marketing': -5,
      'entertainment': -10,
      'other': -5
    };
    
    score += categoryAdjustments[sub.category] || 0;
    
    return Math.max(0, Math.min(100, Math.round(score)));
  }

  /**
   * Normalize cost to monthly
   */
  normalizeMonthlyCost(sub) {
    const cost = sub.cost || 0;
    switch (sub.billingCycle) {
      case 'yearly': return cost / 12;
      case 'quarterly': return cost / 3;
      case 'weekly': return cost * 4.33;
      default: return cost;
    }
  }

  /**
   * Get classified subscriptions grouped by action
   */
  getByAction() {
    const groups = {
      cancelImmediately: [],
      downgrade: [],
      review: [],
      keep: [],
      protected: []
    };
    
    for (const sub of this.subscriptions.values()) {
      const action = sub.classification?.action || 'review';
      switch (action) {
        case 'cancel_immediately':
          groups.cancelImmediately.push(sub);
          break;
        case 'downgrade':
          groups.downgrade.push(sub);
          break;
        case 'review':
          groups.review.push(sub);
          break;
        case 'protected':
          groups.protected.push(sub);
          break;
        default:
          groups.keep.push(sub);
      }
    }
    
    // Sort by priority and cost
    for (const key of Object.keys(groups)) {
      groups[key].sort((a, b) => {
        const priorityDiff = (a.classification?.priority === 'high' ? 3 : a.classification?.priority === 'medium' ? 2 : 1) -
                           (b.classification?.priority === 'high' ? 3 : b.classification?.priority === 'medium' ? 2 : 1);
        if (priorityDiff !== 0) return -priorityDiff;
        return (b.classification?.monthlyCost || 0) - (a.classification?.monthlyCost || 0);
      });
    }
    
    return groups;
  }

  /**
   * Get complete report
   */
  getReport() {
    const byAction = this.getByAction();
    const totalMonthly = Array.from(this.subscriptions.values())
      .reduce((sum, sub) => sum + (sub.classification?.monthlyCost || 0), 0);
    
    const savingsKill = byAction.cancelImmediately.reduce((sum, sub) => 
      sum + (sub.classification?.monthlyCost || 0), 0);
    const savingsDowngrade = byAction.downgrade.reduce((sum, sub) => 
      sum + (sub.classification?.monthlyCost || 0) * 0.3, 0);
    const savingsReview = byAction.review.reduce((sum, sub) => 
      sum + (sub.classification?.monthlyCost || 0) * 0.5, 0);
    const savingsPotential = savingsKill + savingsDowngrade + savingsReview;
    
    return {
      generatedAt: new Date().toISOString(),
      summary: {
        totalSubscriptions: this.subscriptions.size,
        totalMonthlyCost: totalMonthly,
        totalYearlyCost: totalMonthly * 12,
        cancelImmediately: byAction.cancelImmediately.length,
        downgrade: byAction.downgrade.length,
        review: byAction.review.length,
        keep: byAction.keep.length,
        protected: byAction.protected.length,
        savingsPotential,
        savingsBreakdown: { kill: savingsKill, downgrade: savingsDowngrade, review: savingsReview }
      },
      byAction,
      byCategory: this.getByCategory()
    };
  }

  getByCategory() {
    const groups = {};
    for (const sub of this.subscriptions.values()) {
      const cat = sub.category || 'other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(sub);
    }
    return groups;
  }

  /**
   * Mark subscription as protected (will not be cancelled)
   */
  protectSubscription(id, reason = '') {
    const sub = this.subscriptions.get(id);
    if (!sub) {
      throw new Error(`Subscription ${id} not found`);
    }
    
    sub.protected = true;
    sub.protectedReason = reason || 'Manuell geschützt';
    sub.protectedAt = new Date().toISOString();
    this.subscriptions.set(id, sub);
    this.classifyAll();
    this.saveClassified();
    
    this.logger.info?.('classifier.protected', { id, reason: sub.protectedReason });
    return sub;
  }

  /**
   * Remove protected status
   */
  unprotectSubscription(id) {
    const sub = this.subscriptions.get(id);
    if (!sub) {
      throw new Error(`Subscription ${id} not found`);
    }
    
    delete sub.protected;
    delete sub.protectedReason;
    delete sub.protectedAt;
    this.subscriptions.set(id, sub);
    this.classifyAll();
    this.saveClassified();
    
    return sub;
  }

  daysSince(dateString) {
    if (!dateString) return 999;
    const date = new Date(dateString);
    const now = new Date();
    return Math.floor((now - date) / (1000 * 60 * 60 * 24));
  }
}

module.exports = { SubscriptionClassifier };
