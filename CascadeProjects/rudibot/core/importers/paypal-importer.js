const fs = require('fs');
const path = require('path');

/**
 * PayPal Importer — Importiert Transaktionen und identifiziert Abos
 * 
 * Unterstützt:
 * - CSV-Export aus PayPal
 * - API-Integration (mit OAuth)
 * - Automatische Abo-Erkennung
 * - Wiederkehrende Zahlungen
 */

class PayPalImporter {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../../../state/paypal');
    this.clientId = options.clientId || process.env.PAYPAL_CLIENT_ID;
    this.secret = options.secret || process.env.PAYPAL_SECRET;
    this.transactions = [];
    this.detectedSubscriptions = new Map();
    
    this.ensureStorageDir();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  /**
   * Import aus PayPal CSV-Export
   * Format: Date, Time, TimeZone, Name, Type, Status, Currency, Gross, Fee, Net, FromEmail, ToEmail, TransactionID
   */
  async importCSV(filePath) {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n').filter(l => l.trim());
    const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
    
    const transactions = [];
    
    for (let i = 1; i < lines.length; i++) {
      const values = this.parseCSVLine(lines[i]);
      if (values.length < 5) continue;
      
      const tx = {};
      headers.forEach((h, idx) => {
        tx[h] = values[idx] || '';
      });
      
      transactions.push({
        id: tx['Transaction ID'] || `tx_${i}`,
        date: tx['Date'] || '',
        time: tx['Time'] || '',
        name: tx['Name'] || '',
        type: tx['Type'] || '',
        status: tx['Status'] || '',
        currency: tx['Currency'] || 'EUR',
        gross: this.parseAmount(tx['Gross']),
        fee: this.parseAmount(tx['Fee']),
        net: this.parseAmount(tx['Net']),
        fromEmail: tx['From Email Address'] || '',
        toEmail: tx['To Email Address'] || '',
        source: 'paypal'
      });
    }
    
    this.transactions = transactions;
    this.saveTransactions();
    
    // Erkenne Abos
    this.detectSubscriptions();
    
    return {
      imported: transactions.length,
      transactions,
      subscriptions: Array.from(this.detectedSubscriptions.values())
    };
  }

  /**
   * Parse CSV line with quoted fields
   */
  parseCSVLine(line) {
    const result = [];
    let current = '';
    let inQuotes = false;
    
    for (const char of line) {
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        result.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    result.push(current.trim());
    return result;
  }

  /**
   * Parse amount string to number
   */
  parseAmount(amountStr) {
    if (!amountStr) return 0;
    const clean = amountStr.replace(/"/g, '').replace(',', '').trim();
    const num = parseFloat(clean);
    return isNaN(num) ? 0 : num;
  }

  /**
   * Detect recurring payments / subscriptions from transactions
   */
  detectSubscriptions() {
    const vendorPayments = {};
    
    for (const tx of this.transactions) {
      if (tx.type !== 'Subscription Payment' && tx.type !== 'Recurring Payment') continue;
      if (tx.status !== 'Completed') continue;
      
      const vendor = tx.name || tx.toEmail;
      if (!vendor) continue;
      
      if (!vendorPayments[vendor]) {
        vendorPayments[vendor] = [];
      }
      vendorPayments[vendor].push(tx);
    }
    
    // Identify recurring patterns
    for (const [vendor, payments] of Object.entries(vendorPayments)) {
      if (payments.length < 2) continue;
      
      const sorted = payments.sort((a, b) => new Date(a.date) - new Date(b.date));
      const firstPayment = sorted[0];
      const lastPayment = sorted[sorted.length - 1];
      const avgAmount = payments.reduce((sum, p) => sum + Math.abs(p.gross), 0) / payments.length;
      
      // Calculate interval
      const daysDiff = (new Date(lastPayment.date) - new Date(firstPayment.date)) / (1000 * 60 * 60 * 24);
      const intervalDays = Math.round(daysDiff / (payments.length - 1));
      
      let billingCycle = 'unknown';
      if (intervalDays >= 25 && intervalDays <= 35) billingCycle = 'monthly';
      else if (intervalDays >= 85 && intervalDays <= 95) billingCycle = 'quarterly';
      else if (intervalDays >= 360 && intervalDays <= 370) billingCycle = 'yearly';
      
      this.detectedSubscriptions.set(vendor, {
        id: `sub_${vendor.toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
        name: vendor,
        platform: 'PayPal',
        cost: Math.abs(avgAmount),
        currency: firstPayment.currency,
        billingCycle,
        paymentCount: payments.length,
        firstPayment: firstPayment.date,
        lastPayment: lastPayment.date,
        intervalDays,
        source: 'paypal_import',
        detectedAt: new Date().toISOString()
      });
    }
    
    return Array.from(this.detectedSubscriptions.values());
  }

  /**
   * Get all detected subscriptions
   */
  getDetectedSubscriptions() {
    return Array.from(this.detectedSubscriptions.values());
  }

  /**
   * Get transaction summary
   */
  getSummary() {
    const totalSpent = this.transactions
      .filter(t => t.gross < 0)
      .reduce((sum, t) => sum + Math.abs(t.gross), 0);
    
    const totalReceived = this.transactions
      .filter(t => t.gross > 0)
      .reduce((sum, t) => sum + t.gross, 0);
    
    const subscriptionSpent = Array.from(this.detectedSubscriptions.values())
      .reduce((sum, sub) => sum + sub.cost, 0);
    
    return {
      totalTransactions: this.transactions.length,
      totalSpent,
      totalReceived,
      netTotal: totalReceived - totalSpent,
      detectedSubscriptions: this.detectedSubscriptions.size,
      monthlySubscriptionCost: subscriptionSpent,
      yearlySubscriptionCost: subscriptionSpent * 12
    };
  }

  saveTransactions() {
    try {
      const filePath = path.join(this.storagePath, 'transactions.json');
      fs.writeFileSync(filePath, JSON.stringify({
        updatedAt: new Date().toISOString(),
        transactions: this.transactions
      }, null, 2));
    } catch (err) {
      this.logger.error?.('paypal.save_failed', { error: err.message });
    }
  }
}

module.exports = { PayPalImporter };
