const fs = require('fs');
const path = require('path');

/**
 * Protection List — Sensible Bereiche vor Kündigungen schützen
 * 
 * Geschützte Kategorien:
 * - ELSTER & Steuer-Infrastruktur
 * - Domains & Core Hosting
 * - Zahlungs- & Banking-Systeme
 * - Rechtliche & Compliance-Tools
 * - Kritische Business-Infrastruktur
 */

class ProtectionList {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../state/protection');
    
    this.protectedCategories = {
      'tax_infrastructure': {
        name: 'Steuer-Infrastruktur',
        priority: 1,
        color: '#DC2626',
        description: 'ELSTER, Steuerberatung, Finanzamt-Tools',
        keywords: ['elster', 'steuer', 'finanzamt', 'tax', 'bmf', 'idnow', 'trustcenter'],
        vendors: ['ELSTER', 'IDnow', 'TrustCenter', 'DATEV', 'Lexware', 'Buhl'],
        autoProtect: true,
        requiresManualApproval: false
      },
      'domains_core': {
        name: 'Domains & Core Hosting',
        priority: 1,
        color: '#DC2626',
        description: 'Domain-Registrierung, DNS, Core-Webhosting',
        keywords: ['domain', 'dns', 'webhosting', 'server', 'vps', 'cloud hosting'],
        vendors: ['IONOS', 'Strato', 'Hetzner', 'DomainFactory', '1und1'],
        autoProtect: true,
        requiresManualApproval: false
      },
      'payment_infrastructure': {
        name: 'Zahlungs-Infrastruktur',
        priority: 1,
        color: '#DC2626',
        description: 'Banking, Payment-Gateways, Stripe, PayPal Business',
        keywords: ['payment', 'banking', 'stripe', 'paypal business', 'kreditkarte', 'sepa'],
        vendors: ['Stripe', 'PayPal', 'Klarna', 'Adyen', 'Wirecard', 'Sparkasse'],
        autoProtect: true,
        requiresManualApproval: false
      },
      'legal_compliance': {
        name: 'Rechtliche & Compliance',
        priority: 1,
        color: '#DC2626',
        description: 'Rechtliche Tools, DSGVO, Impressum, AGB',
        keywords: ['legal', 'compliance', 'dsgvo', 'impressum', 'agb', 'rechtsschutz'],
        vendors: ['LegalZoom', 'LawDepot', 'Huk24', 'ARAG', 'Allianz'],
        autoProtect: true,
        requiresManualApproval: false
      },
      'business_critical': {
        name: 'Kritische Business-Infrastruktur',
        priority: 2,
        color: '#F59E0B',
        description: 'Shopify, CRM, ERP, E-Mail-Marketing',
        keywords: ['shopify', 'crm', 'erp', 'email marketing', 'automation'],
        vendors: ['Shopify', 'HubSpot', 'Salesforce', 'Mailchimp', 'Klaviyo'],
        autoProtect: false,
        requiresManualApproval: true
      },
      'development_tools': {
        name: 'Development & Tools',
        priority: 3,
        color: '#3B82F6',
        description: 'GitHub, Development-Tools, APIs',
        keywords: ['github', 'development', 'api', 'coding', 'programming'],
        vendors: ['GitHub', 'GitLab', 'Bitbucket', 'Vercel', 'Netlify'],
        autoProtect: false,
        requiresManualApproval: false
      }
    };
    
    this.manualProtections = new Map();
    this.ensureStorageDir();
    this.loadProtections();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadProtections() {
    try {
      const filePath = path.join(this.storagePath, 'protection-list.json');
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        this.manualProtections = new Map(data.manualProtections || []);
      }
    } catch (err) {
      this.logger.error?.('protection.load_failed', { error: err.message });
    }
  }

  saveProtections() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'protection-list.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          manualProtections: Array.from(this.manualProtections.entries())
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('protection.save_failed', { error: err.message });
    }
  }

  /**
   * Prüft ob ein Abo geschützt ist
   */
  isProtected(subscription) {
    const { name, vendor, category, cost, billingCycle, description } = subscription;
    
    // 1. Automatische Kategorie-Prüfung
    for (const [catKey, catConfig] of Object.entries(this.protectedCategories)) {
      if (this.matchesCategory(subscription, catConfig)) {
        return {
          protected: true,
          category: catKey,
          reason: catConfig.description,
          autoProtected: catConfig.autoProtect,
          requiresApproval: catConfig.requiresManualApproval,
          priority: catConfig.priority
        };
      }
    }
    
    // 2. Manuelle Schutz-Prüfung
    for (const [id, protection] of this.manualProtections) {
      if (this.matchesManualProtection(subscription, protection)) {
        return {
          protected: true,
          category: 'manual',
          reason: protection.reason || 'Manuell geschützt',
          autoProtected: false,
          requiresApproval: protection.requiresApproval || false,
          priority: protection.priority || 3
        };
      }
    }
    
    // 3. Hohe Beträge (>100€/Monat) benötigen Approval
    const monthlyCost = this.normalizeMonthlyCost(subscription);
    if (monthlyCost > 100) {
      return {
        protected: true,
        category: 'high_value',
        reason: `Hoher Betrag: €${monthlyCost.toFixed(2)}/Monat`,
        autoProtected: false,
        requiresApproval: true,
        priority: 2
      };
    }
    
    return { protected: false };
  }

  /**
   * Prüft ob Abo zu einer geschützten Kategorie passt
   */
  matchesCategory(subscription, category) {
    const { name = '', vendor = '', description = '' } = subscription;
    const searchText = `${name} ${vendor} ${description}`.toLowerCase();
    
    // Keyword-Prüfung
    for (const keyword of category.keywords) {
      if (searchText.includes(keyword.toLowerCase())) {
        return true;
      }
    }
    
    // Vendor-Prüfung
    for (const vendorName of category.vendors) {
      if (vendor.toLowerCase().includes(vendorName.toLowerCase()) || 
          name.toLowerCase().includes(vendorName.toLowerCase())) {
        return true;
      }
    }
    
    return false;
  }

  /**
   * Prüft ob Abo zu manuellem Schutz passt
   */
  matchesManualProtection(subscription, protection) {
    const { name = '', vendor = '', cost = 0 } = subscription;
    
    // Exakte Namens-Übereinstimmung
    if (protection.name && name.toLowerCase().includes(protection.name.toLowerCase())) {
      return true;
    }
    
    // Vendor-Übereinstimmung
    if (protection.vendor && vendor.toLowerCase().includes(protection.vendor.toLowerCase())) {
      return true;
    }
    
    // Kosten-Übereinstimmung
    if (protection.cost && Math.abs(cost - protection.cost) < 0.01) {
      return true;
    }
    
    return false;
  }

  /**
   * Manuellen Schutz hinzufügen
   */
  addManualProtection(protection) {
    const id = `manual_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    const protectionData = {
      id,
      name: protection.name,
      vendor: protection.vendor,
      cost: protection.cost,
      reason: protection.reason || 'Manuell geschützt',
      priority: protection.priority || 3,
      requiresApproval: protection.requiresApproval || false,
      createdAt: new Date().toISOString(),
      expiresAt: protection.expiresAt || null
    };
    
    this.manualProtections.set(id, protectionData);
    this.saveProtections();
    
    this.logger.info?.('protection.manual_added', { id, name: protection.name, reason: protection.reason });
    return protectionData;
  }

  /**
   * Manuellen Schutz entfernen
   */
  removeManualProtection(id) {
    const removed = this.manualProtections.delete(id);
    if (removed) {
      this.saveProtections();
      this.logger.info?.('protection.manual_removed', { id });
    }
    return removed;
  }

  /**
   * Alle geschützten Abos filtern
   */
  filterProtectedSubscriptions(subscriptions) {
    const protectedItems = [];
    const unprotectedItems = [];
    
    for (const sub of subscriptions) {
      const protection = this.isProtected(sub);
      if (protection.protected) {
        protectedItems.push({
          ...sub,
          protection
        });
      } else {
        unprotectedItems.push(sub);
      }
    }
    
    return { protected: protectedItems, unprotected: unprotectedItems };
  }

  /**
   * Kündigungs-Empfehlung basierend auf Schutzstatus
   */
  getCancellationRecommendation(subscription) {
    const protection = this.isProtected(subscription);
    
    if (protection.protected) {
      if (protection.requiresApproval) {
        return {
          action: 'review',
          priority: 'high',
          reason: `Geschützt: ${protection.reason} — Manuelle Freigabe erforderlich`,
          needsApproval: true,
          approvalType: 'manual'
        };
      } else {
        return {
          action: 'protected',
          priority: 'none',
          reason: `Kritisch geschützt: ${protection.reason}`,
          needsApproval: false
        };
      }
    }
    
    // Normale Kündigungslogik
    const monthlyCost = this.normalizeMonthlyCost(subscription);
    const daysSinceLastUse = this.daysSince(subscription.lastPayment || subscription.lastUsed);
    
    if (daysSinceLastUse > 30 && monthlyCost < 50) {
      return {
        action: 'cancel_immediately',
        priority: 'high',
        reason: `30+ Tage ungenutzt, €${monthlyCost.toFixed(2)}/Monat`,
        needsApproval: false
      };
    }
    
    if (daysSinceLastUse > 30) {
      return {
        action: 'review',
        priority: 'medium',
        reason: `30+ Tage ungenutzt, aber kritisch oder teuer`,
        needsApproval: true
      };
    }
    
    return {
      action: 'keep',
      priority: 'low',
      reason: 'Aktiv genutzt',
      needsApproval: false
    };
  }

  /**
   * Schutz-Report
   */
  getProtectionReport(subscriptions) {
    const { protected: protectedItems, unprotected: unprotectedItems } = this.filterProtectedSubscriptions(subscriptions);
    
    const byCategory = {};
    for (const sub of protectedItems) {
      const cat = sub.protection.category;
      if (!byCategory[cat]) byCategory[cat] = [];
      byCategory[cat].push(sub);
    }
    
    const totalMonthlyCost = subscriptions.reduce((sum, sub) => sum + this.normalizeMonthlyCost(sub), 0);
    const protectedCost = protectedItems.reduce((sum, sub) => sum + this.normalizeMonthlyCost(sub), 0);
    
    return {
      generatedAt: new Date().toISOString(),
      summary: {
        totalSubscriptions: subscriptions.length,
        protectedSubscriptions: protectedItems.length,
        unprotectedSubscriptions: unprotectedItems.length,
        totalMonthlyCost,
        protectedMonthlyCost: protectedCost,
        unprotectedMonthlyCost: totalMonthlyCost - protectedCost,
        protectionRate: (protectedItems.length / subscriptions.length * 100).toFixed(1)
      },
      categories: byCategory,
      protectedSubscriptions: protectedItems,
      unprotectedSubscriptions: unprotectedItems,
      manualProtections: Array.from(this.manualProtections.values())
    };
  }

  /**
   * Hilfsfunktionen
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

  daysSince(dateString) {
    if (!dateString) return 999;
    const date = new Date(dateString);
    const now = new Date();
    return Math.floor((now - date) / (1000 * 60 * 60 * 24));
  }

  /**
   * Get all protection categories
   */
  getCategories() {
    return this.protectedCategories;
  }

  /**
   * Get manual protections
   */
  getManualProtections() {
    return Array.from(this.manualProtections.values());
  }
}

module.exports = { ProtectionList };
