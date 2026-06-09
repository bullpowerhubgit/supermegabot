#!/usr/bin/env node

// 🎯 SUBSCRIPTION HUNTER
// Rudolf Sarkany · Automated Subscription Detection & Management
// ===================================================

'use strict';

const fs = require('fs').promises;
const path = require('path');

const DATA_PATH = path.join(__dirname, 'subscriptions.json');

// ── Default Provider Registry ──────────────────────────────────
const DEFAULT_PROVIDERS = {
  netflix: { provider: 'netflix', channel: 'web', noticeDays: 0, supportsOnlineCancel: true, requiresCustomerNumber: false, cancelUrl: 'https://www.netflix.com/cancelplan', category: 'entertainment' },
  spotify: { provider: 'spotify', channel: 'web', noticeDays: 0, supportsOnlineCancel: true, requiresCustomerNumber: false, cancelUrl: 'https://www.spotify.com/account/cancel', category: 'entertainment' },
  amazon_prime: { provider: 'amazon_prime', channel: 'web', noticeDays: 0, supportsOnlineCancel: true, requiresCustomerNumber: false, cancelUrl: 'https://www.amazon.de/gp/membership/cancel', category: 'shopping' },
  adobe: { provider: 'adobe', channel: 'web', noticeDays: 14, supportsOnlineCancel: true, requiresCustomerNumber: false, cancelUrl: 'https://account.adobe.com/plans', category: 'software' },
  microsoft365: { provider: 'microsoft365', channel: 'web', noticeDays: 30, supportsOnlineCancel: true, requiresCustomerNumber: false, cancelUrl: 'https://account.microsoft.com/services', category: 'software' },
  gym: { provider: 'gym', channel: 'manual-letter', noticeDays: 30, supportsOnlineCancel: false, requiresCustomerNumber: true, category: 'health' },
  mobile: { provider: 'mobile', channel: 'email', noticeDays: 30, supportsOnlineCancel: false, requiresCustomerNumber: true, category: 'telecommunication' },
  insurance: { provider: 'insurance', channel: 'manual-letter', noticeDays: 90, supportsOnlineCancel: false, requiresCustomerNumber: true, category: 'insurance' }
};

// ── Subscription Hunter ──────────────────────────────────────────
class SubscriptionHunter {
  constructor() {
    this.subscriptions = [];
    this.providers = { ...DEFAULT_PROVIDERS };
    this.totalMonthly = 0;
  }

  async init() {
    try {
      const data = await fs.readFile(DATA_PATH, 'utf8');
      const parsed = JSON.parse(data);
      this.subscriptions = parsed.subscriptions || [];
      this.providers = { ...this.providers, ...(parsed.customProviders || {}) };
      this.calculateTotal();
      console.log('🎯 Subscription Hunter initialized');
    } catch (error) {
      console.log('🎯 Subscription Hunter initialized (empty)');
    }
  }

  async save() {
    await fs.writeFile(DATA_PATH, JSON.stringify({
      subscriptions: this.subscriptions,
      customProviders: this.providers,
      updated: new Date().toISOString()
    }, null, 2), 'utf8');
  }

  // ── Detection ────────────────────────────────────────────────
  detectFromEmail(emailSubject, emailBody) {
    const detections = [];
    const text = (emailSubject + ' ' + emailBody).toLowerCase();
    
    for (const [key, provider] of Object.entries(this.providers)) {
      if (text.includes(provider.provider.toLowerCase()) || 
          text.includes(provider.category)) {
        detections.push({
          provider: key,
          confidence: 'high',
          category: provider.category,
          source: 'email'
        });
      }
    }
    
    // Detect generic subscription patterns
    const subPatterns = [
      /abo/i, /subscription/i, /membership/i, /premium/i,
      /monatlich/i, /monthly/i, /jahrlich/i, /annual/i,
      /EUR[\s]*(\d+[,.]\d{2})/, /(\d+[,.]\d{2})[\s]*EUR/,
      /(\d+[,.]\d{2})[\s]*€/
    ];
    
    for (const pattern of subPatterns) {
      const matches = text.match(pattern);
      if (matches) {
        detections.push({
          pattern: pattern.toString(),
          match: matches[0],
          confidence: 'medium',
          source: 'pattern'
        });
      }
    }
    
    return detections;
  }

  detectFromTransaction(description, amount) {
    const detections = [];
    const text = description.toLowerCase();
    
    for (const [key, provider] of Object.entries(this.providers)) {
      if (text.includes(provider.provider.toLowerCase())) {
        detections.push({
          provider: key,
          amount,
          confidence: 'high',
          category: provider.category,
          source: 'transaction'
        });
      }
    }
    
    return detections;
  }

  // ── Management ────────────────────────────────────────────────
  addSubscription(subscription) {
    const sub = {
      id: crypto.randomUUID(),
      ...subscription,
      detectedAt: new Date().toISOString(),
      status: 'active',
      nextCheck: this.calculateNextCheck(subscription)
    };
    
    this.subscriptions.push(sub);
    this.calculateTotal();
    this.save();
    
    return sub;
  }

  calculateNextCheck(subscription) {
    const now = new Date();
    if (subscription.cycle === 'monthly') {
      now.setMonth(now.getMonth() + 1);
    } else if (subscription.cycle === 'annual') {
      now.setFullYear(now.getFullYear() + 1);
    }
    return now.toISOString();
  }

  calculateTotal() {
    this.totalMonthly = this.subscriptions
      .filter(s => s.status === 'active')
      .reduce((sum, s) => sum + (s.monthlyCost || 0), 0);
  }

  getUpcomingRenewals(days = 7) {
    const now = new Date();
    const limit = new Date(now.getTime() + days * 24 * 60 * 60 * 1000);
    
    return this.subscriptions
      .filter(s => s.status === 'active')
      .filter(s => {
        const next = new Date(s.nextBilling);
        return next >= now && next <= limit;
      })
      .sort((a, b) => new Date(a.nextBilling) - new Date(b.nextBilling));
  }

  getKillableSubscriptions() {
    return this.subscriptions
      .filter(s => s.status === 'active')
      .filter(s => {
        const provider = this.providers[s.provider];
        if (!provider) return false;
        return provider.noticeDays <= 30 || provider.supportsOnlineCancel;
      });
  }

  getSummary() {
    const active = this.subscriptions.filter(s => s.status === 'active');
    const categories = {};
    
    for (const sub of active) {
      const provider = this.providers[sub.provider];
      const cat = provider ? provider.category : 'unknown';
      categories[cat] = (categories[cat] || 0) + (sub.monthlyCost || 0);
    }
    
    return {
      totalActive: active.length,
      totalMonthly: this.totalMonthly,
      totalAnnual: this.totalMonthly * 12,
      categories,
      upcomingRenewals: this.getUpcomingRenewals(7).length,
      killable: this.getKillableSubscriptions().length
    };
  }

  // ── Cancellation Prep ────────────────────────────────────────
  async prepareCancellation(subscriptionId) {
    const sub = this.subscriptions.find(s => s.id === subscriptionId);
    if (!sub) return { error: 'Subscription not found' };
    
    const provider = this.providers[sub.provider];
    if (!provider) return { error: 'Provider not registered' };
    
    const eligibility = this.checkEligibility(sub, provider);
    
    return {
      subscription: sub,
      provider,
      eligibility,
      canCancel: eligibility.eligible,
      nextSteps: this.getNextSteps(provider, eligibility)
    };
  }

  checkEligibility(subscription, provider) {
    if (!subscription.nextBilling) {
      return { eligible: false, reason: 'No billing date' };
    }
    
    const now = new Date();
    const nextBilling = new Date(subscription.nextBilling);
    const daysUntil = Math.ceil((nextBilling - now) / (1000 * 60 * 60 * 24));
    
    if (daysUntil < provider.noticeDays) {
      return { 
        eligible: false, 
        reason: `Notice period too short. Need ${provider.noticeDays} days, have ${daysUntil}`,
        daysUntil,
        noticeDays: provider.noticeDays
      };
    }
    
    return { 
      eligible: true, 
      daysUntil,
      noticeDays: provider.noticeDays,
      reason: 'Ready to cancel'
    };
  }

  getNextSteps(provider, eligibility) {
    if (!eligibility.eligible) {
      return [`Wait until ${eligibility.noticeDays} days before renewal`];
    }
    
    if (provider.supportsOnlineCancel) {
      return ['Open cancellation URL', 'Confirm cancellation', 'Save confirmation'];
    }
    
    if (provider.channel === 'email') {
      return ['Prepare cancellation email', 'Send to provider', 'Wait for confirmation'];
    }
    
    return ['Prepare written cancellation', 'Send via registered mail', 'Keep proof of sending'];
  }
}

module.exports = { SubscriptionHunter, DEFAULT_PROVIDERS };

// ── CLI ─────────────────────────────────────────────────────────
if (require.main === module) {
  const hunter = new SubscriptionHunter();
  hunter.init().then(() => {
    console.log('🎯 Subscription Hunter ready');
    console.log('Summary:', hunter.getSummary());
  });
}
