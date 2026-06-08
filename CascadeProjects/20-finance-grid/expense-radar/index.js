#!/usr/bin/env node

// 💰 EXPENSE RADAR
// Rudolf Sarkany · Income & Expense Tracking with Auto-Categorization
// ===================================================

'use strict';

const fs = require('fs').promises;
const path = require('path');

const DATA_PATH = path.join(__dirname, 'transactions.json');

// ── German Tax Categories ───────────────────────────────────────
const TAX_CATEGORIES = {
  private: ['lebensmittel', 'miete', 'strom', 'internet', 'handy', 'versicherung', 'kleidung', 'freizeit', 'urlaub', 'gesundheit'],
  selbstaendig: ['buero', 'werkzeuge', 'software', 'hardware', 'weiterbildung', 'fachliteratur', 'fortbildung', 'coaching'],
  gewerbe: ['werbung', 'marketing', 'reisekosten', 'bewirtung', 'bueromiete', 'material', 'lager', 'versand'],
  mixed: ['auto', 'bahn', 'taxi', 'flug', 'hotel', 'mahlzeiten']
};

const AUTO_CATEGORIES = {
  // Software & SaaS
  'github': 'software', 'vercel': 'software', 'railway': 'software', 'digitalocean': 'software',
  'aws': 'software', 'google cloud': 'software', 'azure': 'software',
  'openai': 'software', 'anthropic': 'software', 'perplexity': 'software',
  'notion': 'software', 'figma': 'software', 'linear': 'software',
  'shopify': 'software', 'stripe': 'software', 'twilio': 'software',
  
  // Marketing
  'google ads': 'werbung', 'facebook ads': 'werbung', 'meta ads': 'werbung',
  'tiktok ads': 'werbung', 'amazon ads': 'werbung', 'pinterest ads': 'werbung',
  'mailchimp': 'werbung', 'klaviyo': 'werbung', 'sendgrid': 'werbung',
  
  // Infrastructure
  'cloudflare': 'software', 'namecheap': 'software', 'godaddy': 'software',
  'ionos': 'software', 'strato': 'software', 'hosteurope': 'software',
  
  // Entertainment
  'netflix': 'freizeit', 'spotify': 'freizeit', 'amazon prime': 'freizeit',
  'disney': 'freizeit', 'apple tv': 'freizeit', 'youtube premium': 'freizeit',
  
  // Telecommunication
  'telekom': 'handy', 'vodafone': 'handy', 'o2': 'handy', '1&1': 'handy',
  'congstar': 'handy', 'aldi talk': 'handy',
  
  // Insurance
  'allianz': 'versicherung', 'huk': 'versicherung', 'cosmos': 'versicherung',
  'ergo': 'versicherung', 'axa': 'versicherung', 'generali': 'versicherung'
};

// ── Expense Radar ──────────────────────────────────────────────
class ExpenseRadar {
  constructor() {
    this.transactions = [];
    this.categories = { ...TAX_CATEGORIES };
  }

  async init() {
    try {
      const data = await fs.readFile(DATA_PATH, 'utf8');
      const parsed = JSON.parse(data);
      this.transactions = parsed.transactions || [];
      console.log('💰 Expense Radar initialized');
    } catch (error) {
      console.log('💰 Expense Radar initialized (empty)');
    }
  }

  async save() {
    await fs.writeFile(DATA_PATH, JSON.stringify({
      transactions: this.transactions,
      updated: new Date().toISOString()
    }, null, 2), 'utf8');
  }

  // ── Auto-Categorization ──────────────────────────────────────
  autoCategorize(description, amount) {
    const text = description.toLowerCase();
    
    // Check known vendors
    for (const [vendor, category] of Object.entries(AUTO_CATEGORIES)) {
      if (text.includes(vendor)) {
        return { category, confidence: 'high', source: 'vendor_match' };
      }
    }
    
    // Check keywords
    const keywords = {
      'software': /(software|app|tool|saas|subscription|license)/i,
      'werbung': /(ad|ads|advertising|marketing|campaign|promotion)/i,
      'bueromiete': /(rent|miete|office|buro)/i,
      'reisekosten': /(flight|hotel|train|bahn|flight|uber|taxi)/i,
      'bewirtung': /(restaurant|essen|food|lunch|dinner|catering)/i,
      'hardware': /(laptop|computer|monitor|keyboard|mouse|phone|iphone)/i,
      'weiterbildung': /(course|kurs|training|seminar|workshop|buch|book)/i
    };
    
    for (const [category, pattern] of Object.entries(keywords)) {
      if (pattern.test(text)) {
        return { category, confidence: 'medium', source: 'keyword_match' };
      }
    }
    
    // Amount-based heuristics
    if (amount < 20) return { category: 'kleinbetrage', confidence: 'low', source: 'amount_heuristic' };
    if (amount > 500) return { category: 'investition', confidence: 'low', source: 'amount_heuristic' };
    
    return { category: 'unbekannt', confidence: 'low', source: 'fallback' };
  }

  // ── Transaction Management ────────────────────────────────────
  addTransaction(data) {
    const categorization = this.autoCategorize(data.description, data.amount);
    
    const transaction = {
      id: crypto.randomUUID(),
      date: data.date || new Date().toISOString(),
      description: data.description,
      amount: parseFloat(data.amount),
      type: data.amount >= 0 ? 'income' : 'expense',
      category: data.category || categorization.category,
      autoCategorized: !data.category,
      confidence: categorization.confidence,
      source: data.source || 'manual',
      tags: data.tags || [],
      taxRelevant: data.taxRelevant !== undefined ? data.taxRelevant : true,
      created: new Date().toISOString()
    };
    
    this.transactions.push(transaction);
    this.save();
    
    return transaction;
  }

  // ── Analysis ─────────────────────────────────────────────────
  getMonthlySummary(year, month) {
    const filtered = this.transactions.filter(t => {
      const d = new Date(t.date);
      return d.getFullYear() === year && d.getMonth() === month - 1;
    });
    
    const income = filtered.filter(t => t.type === 'income').reduce((sum, t) => sum + t.amount, 0);
    const expenses = filtered.filter(t => t.type === 'expense').reduce((sum, t) => sum + Math.abs(t.amount), 0);
    
    const byCategory = {};
    for (const t of filtered) {
      byCategory[t.category] = (byCategory[t.category] || 0) + Math.abs(t.amount);
    }
    
    return {
      year, month,
      income,
      expenses,
      balance: income - expenses,
      transactionCount: filtered.length,
      byCategory: Object.entries(byCategory)
        .map(([cat, amount]) => ({ category: cat, amount }))
        .sort((a, b) => b.amount - a.amount)
    };
  }

  getTaxRelevantExpenses(year) {
    return this.transactions
      .filter(t => {
        const d = new Date(t.date);
        return d.getFullYear() === year && t.taxRelevant && t.type === 'expense';
      })
      .map(t => ({
        date: t.date,
        description: t.description,
        amount: Math.abs(t.amount),
        category: t.category
      }));
  }

  detectAnomalies() {
    const monthlyTotals = {};
    
    for (const t of this.transactions) {
      const d = new Date(t.date);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      monthlyTotals[key] = (monthlyTotals[key] || 0) + Math.abs(t.amount);
    }
    
    const values = Object.values(monthlyTotals);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const stdDev = Math.sqrt(values.reduce((sq, n) => sq + Math.pow(n - avg, 2), 0) / values.length);
    
    const anomalies = [];
    for (const [month, total] of Object.entries(monthlyTotals)) {
      if (Math.abs(total - avg) > 2 * stdDev) {
        anomalies.push({ month, total, avg, deviation: total - avg });
      }
    }
    
    return anomalies;
  }

  // ── Export ───────────────────────────────────────────────────
  async exportForTax(year) {
    const expenses = this.getTaxRelevantExpenses(year);
    const categories = {};
    
    for (const exp of expenses) {
      categories[exp.category] = (categories[exp.category] || 0) + exp.amount;
    }
    
    return {
      year,
      totalExpenses: expenses.reduce((sum, e) => sum + e.amount, 0),
      categories: Object.entries(categories).map(([cat, amount]) => ({ category: cat, amount })),
      transactions: expenses
    };
  }
}

module.exports = { ExpenseRadar, TAX_CATEGORIES, AUTO_CATEGORIES };

// ── CLI ─────────────────────────────────────────────────────────
if (require.main === module) {
  const radar = new ExpenseRadar();
  radar.init().then(() => {
    console.log('💰 Expense Radar ready');
  });
}
