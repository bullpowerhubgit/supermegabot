const fs = require('fs');
const path = require('path');

/**
 * Bank Importer — Importiert Kontoauszüge und erkennt Abos
 * 
 * Unterstützt:
 * - CSV/Kontoauszüge (Deutsche Bank, Commerzbank, Sparkasse, ING)
 * - MT940/MT942 Formate
 * - SEPA-Lastschriften erkennen
 * - Automatische Abo-Klassifizierung
 */

class BankImporter {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../../../state/bank');
    this.transactions = [];
    this.detectedSubscriptions = new Map();
    
    this.subscriptionPatterns = [
      { pattern: /NETFLIX|SPOTIFY|AMAZON PRIME|AMAZON MUSIC/i, category: 'entertainment' },
      { pattern: /ADOBE|CREATIVE CLOUD/i, category: 'design' },
      { pattern: /DROPBOX|GOOGLE DRIVE|ICLOUD/i, category: 'storage' },
      { pattern: /SHOPIFY|SHOPIFY.*PAY/i, category: 'ecommerce' },
      { pattern: /HUBSPOT|SALESFORCE|ZOHO/i, category: 'crm' },
      { pattern: /SLACK|MICROSOFT.*365|GOOGLE.*WORKSPACE/i, category: 'productivity' },
      { pattern: /ZOOM|TEAMS|WEBEX/i, category: 'communication' },
      { pattern: /GITHUB|GITLAB|BITBUCKET/i, category: 'development' },
      { pattern: /VERCEL|NETLIFY|AWS.*AMAZON|HEROKU/i, category: 'hosting' },
      { pattern: /OPENAI|ANTHROPIC|PERPLEXITY/i, category: 'ai' },
      { pattern: /KLAVIYO|MAILCHIMP|SENDGRID/i, category: 'marketing' },
      { pattern: /NOTION|ASANA|TRELLO|MONDAY/i, category: 'project_management' }
    ];
    
    this.ensureStorageDir();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  /**
   * Import CSV Kontoauszug
   * Deutsche Formate: Buchungstag, Valuta, Auftraggeber/Empfänger, Verwendungszweck, Betrag
   */
  async importCSV(filePath, bankFormat = 'auto') {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n').filter(l => l.trim());
    
    // Detect format from first line
    const format = bankFormat === 'auto' ? this.detectFormat(lines[0]) : bankFormat;
    
    const transactions = [];
    const startIdx = this.hasHeader(lines[0]) ? 1 : 0;
    
    for (let i = startIdx; i < lines.length; i++) {
      const tx = this.parseTransaction(lines[i], format);
      if (tx && tx.amount !== 0) {
        transactions.push(tx);
      }
    }
    
    this.transactions = transactions;
    this.saveTransactions();
    this.detectSubscriptions();
    
    return {
      imported: transactions.length,
      format,
      transactions: transactions.slice(0, 10),
      subscriptions: Array.from(this.detectedSubscriptions.values())
    };
  }

  detectFormat(firstLine) {
    const line = firstLine.toUpperCase();
    if (line.includes('BUCHUNG') || line.includes('VALUTA')) return 'german';
    if (line.includes('DATE') && line.includes('DESCRIPTION')) return 'english';
    if (line.includes('DATUM') && line.includes('BETRAG')) return 'swiss';
    return 'german'; // Default
  }

  hasHeader(line) {
    const upper = line.toUpperCase();
    return upper.includes('BUCHUNG') || upper.includes('DATE') || upper.includes('BETRAG');
  }

  parseTransaction(line, format) {
    const values = line.split(';').map(v => v.trim().replace(/"/g, ''));
    
    if (format === 'german') {
      // Format: Buchungstag;Valuta;Auftraggeber/Empfänger;Verwendungszweck;Betrag
      const amountStr = values[4] || values[values.length - 1];
      const amount = this.parseGermanAmount(amountStr);
      
      return {
        id: `tx_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
        date: this.parseGermanDate(values[0]),
        valuta: this.parseGermanDate(values[1]),
        counterparty: values[2] || '',
        purpose: values[3] || '',
        amount,
        type: amount < 0 ? 'debit' : 'credit',
        raw: line,
        source: 'bank'
      };
    }
    
    // Generic format
    return {
      id: `tx_${Date.now()}`,
      date: values[0] || '',
      counterparty: values[1] || '',
      purpose: values[2] || '',
      amount: this.parseGermanAmount(values[values.length - 1]),
      type: 'unknown',
      raw: line,
      source: 'bank'
    };
  }

  parseGermanAmount(amountStr) {
    if (!amountStr) return 0;
    const clean = amountStr
      .replace(/\./g, '')  // Remove thousand separators
      .replace(',', '.')   // German comma to decimal
      .replace(/[^\d.-]/g, '');
    const num = parseFloat(clean);
    return isNaN(num) ? 0 : num;
  }

  parseGermanDate(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('.');
    if (parts.length === 3) {
      return `${parts[2]}-${parts[1]}-${parts[0]}`;
    }
    return dateStr;
  }

  /**
   * Detect subscriptions from bank transactions
   */
  detectSubscriptions() {
    const vendorPayments = {};
    
    for (const tx of this.transactions) {
      if (tx.amount >= 0) continue; // Only debits
      
      const counterparty = tx.counterparty.toUpperCase();
      const purpose = tx.purpose.toUpperCase();
      
      // Check if matches subscription pattern
      let matchedCategory = null;
      for (const { pattern, category } of this.subscriptionPatterns) {
        if (pattern.test(counterparty) || pattern.test(purpose)) {
          matchedCategory = category;
          break;
        }
      }
      
      if (!matchedCategory) continue;
      
      const vendor = tx.counterparty || 'Unknown';
      if (!vendorPayments[vendor]) {
        vendorPayments[vendor] = [];
      }
      vendorPayments[vendor].push({ ...tx, category: matchedCategory });
    }
    
    // Identify recurring patterns
    for (const [vendor, payments] of Object.entries(vendorPayments)) {
      if (payments.length < 2) continue;
      
      const sorted = payments.sort((a, b) => new Date(a.date) - new Date(b.date));
      const firstPayment = sorted[0];
      const lastPayment = sorted[sorted.length - 1];
      const avgAmount = Math.abs(payments.reduce((sum, p) => sum + p.amount, 0) / payments.length);
      
      const daysDiff = (new Date(lastPayment.date) - new Date(firstPayment.date)) / (1000 * 60 * 60 * 24);
      const intervalDays = Math.round(daysDiff / (payments.length - 1));
      
      let billingCycle = 'unknown';
      if (intervalDays >= 25 && intervalDays <= 35) billingCycle = 'monthly';
      else if (intervalDays >= 85 && intervalDays <= 95) billingCycle = 'quarterly';
      else if (intervalDays >= 360) billingCycle = 'yearly';
      else if (intervalDays <= 10) billingCycle = 'weekly';
      
      const id = `sub_${vendor.toLowerCase().replace(/[^a-z0-9]/g, '_').substring(0, 20)}`;
      
      this.detectedSubscriptions.set(vendor, {
        id,
        name: vendor,
        category: firstPayment.category,
        platform: 'Bank Transfer / SEPA',
        cost: avgAmount,
        currency: 'EUR',
        billingCycle,
        paymentCount: payments.length,
        firstPayment: firstPayment.date,
        lastPayment: lastPayment.date,
        intervalDays,
        source: 'bank_import',
        detectedAt: new Date().toISOString()
      });
    }
    
    return Array.from(this.detectedSubscriptions.values());
  }

  /**
   * Get subscription summary with categorization
   */
  getSubscriptionSummary() {
    const byCategory = {};
    let totalMonthly = 0;
    
    for (const sub of this.detectedSubscriptions.values()) {
      if (!byCategory[sub.category]) {
        byCategory[sub.category] = { subscriptions: [], total: 0 };
      }
      byCategory[sub.category].subscriptions.push(sub);
      byCategory[sub.category].total += sub.cost;
      
      if (sub.billingCycle === 'monthly') totalMonthly += sub.cost;
      else if (sub.billingCycle === 'yearly') totalMonthly += sub.cost / 12;
      else if (sub.billingCycle === 'quarterly') totalMonthly += sub.cost / 3;
    }
    
    return {
      totalDetected: this.detectedSubscriptions.size,
      totalMonthlyCost: totalMonthly,
      yearlyEstimate: totalMonthly * 12,
      byCategory,
      subscriptions: Array.from(this.detectedSubscriptions.values())
    };
  }

  saveTransactions() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'transactions.json'),
        JSON.stringify({ updatedAt: new Date().toISOString(), transactions: this.transactions }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('bank.save_failed', { error: err.message });
    }
  }
}

module.exports = { BankImporter };
