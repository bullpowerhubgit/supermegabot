#!/usr/bin/env node

// ⚖️ COMPLIANCE ENGINE
// Rudolf Sarkany · Deadline Monitoring & Regulatory Compliance
// ===================================================

'use strict';

const fs = require('fs').promises;
const path = require('path');

const DATA_PATH = path.join(__dirname, 'compliance-data.json');

// ── German Tax Deadlines ───────────────────────────────────────
const TAX_DEADLINES = {
  'einkommensteuer': [
    { month: 5, day: 31, type: 'einkommensteuererklärung', description: 'Einkommensteuererklärung (Selbstaendige)' },
    { month: 7, day: 31, type: 'einkommensteuererklärung', description: 'Einkommensteuererklärung (Mit Steuerberater)' }
  ],
  'umsatzsteuer': [
    { month: 10, day: 10, type: 'zusammenfassende-meldung', description: 'Zusammenfassende Meldung (Q3)' },
    { month: 1, day: 10, type: 'zusammenfassende-meldung', description: 'Zusammenfassende Meldung (Q4)' }
  ],
  'gewerbesteuer': [
    { month: 5, day: 31, type: 'gewerbesteuererklärung', description: 'Gewerbesteuererklärung' }
  ],
  'körperschaftsteuer': [
    { month: 5, day: 31, type: 'körperschaftsteuererklärung', description: 'Körperschaftsteuererklärung' }
  ]
};

const COMPLIANCE_RULES = [
  {
    id: 'receipt-preservation',
    name: 'Belegaufbewahrung',
    description: 'Belege müssen 10 Jahre aufbewahrt werden',
    severity: 'high',
    check: async (data) => {
      const oldDocs = (data.documents || []).filter(d => {
        const age = (Date.now() - new Date(d.date).getTime()) / (1000 * 60 * 60 * 24 * 365);
        return age > 10;
      });
      return { passed: oldDocs.length === 0, details: `${oldDocs.length} alte Belege gefunden` };
    }
  },
  {
    id: 'vat-documentation',
    name: 'USt-Rechnungspflicht',
    description: 'Rechnungen müssen alle Pflichtangaben enthalten',
    severity: 'critical',
    check: async (data) => {
      const issues = [];
      const invoices = (data.documents || []).filter(d => d.type === 'invoice');
      for (const inv of invoices) {
        if (!inv.vatRate) issues.push(`Rechnung ${inv.id}: Kein USt-Satz`);
        if (!inv.invoiceNumber) issues.push(`Rechnung ${inv.id}: Keine Rechnungsnummer`);
      }
      return { passed: issues.length === 0, details: issues.join('; ') || 'OK' };
    }
  },
  {
    id: 'income-declaration',
    name: 'Einkünfte-Erklärung',
    description: 'Alle Einkünfte müssen deklariert sein',
    severity: 'critical',
    check: async (data) => {
      const undeclared = (data.transactions || []).filter(t => t.type === 'income' && !t.declared);
      return { passed: undeclared.length === 0, details: `${undeclared.length} nicht deklarierte Einkünfte` };
    }
  }
];

// ── Compliance Engine ───────────────────────────────────────────
class ComplianceEngine {
  constructor() {
    this.data = {};
    this.deadlines = [];
    this.rules = COMPLIANCE_RULES;
  }

  async init() {
    try {
      const data = await fs.readFile(DATA_PATH, 'utf8');
      this.data = JSON.parse(data);
      this.deadlines = this.data.deadlines || [];
      console.log('⚖️ Compliance Engine initialized');
    } catch (error) {
      console.log('⚖️ Compliance Engine initialized (empty)');
    }
  }

  async save() {
    await fs.writeFile(DATA_PATH, JSON.stringify({
      ...this.data,
      deadlines: this.deadlines,
      updated: new Date().toISOString()
    }, null, 2), 'utf8');
  }

  // ── Deadline Management ────────────────────────────────────────
  addDeadline(deadline) {
    const dl = {
      id: crypto.randomUUID(),
      type: deadline.type,
      description: deadline.description,
      dueDate: deadline.dueDate,
      taxType: deadline.taxType,
      status: 'open',
      priority: this.calculatePriority(deadline.dueDate),
      created: new Date().toISOString()
    };
    
    this.deadlines.push(dl);
    this.save();
    return dl;
  }

  calculatePriority(dueDate) {
    const daysUntil = Math.ceil((new Date(dueDate) - Date.now()) / (1000 * 60 * 60 * 24));
    if (daysUntil < 7) return 'critical';
    if (daysUntil < 14) return 'high';
    if (daysUntil < 30) return 'medium';
    return 'low';
  }

  getUpcomingDeadlines(days = 30) {
    const now = new Date();
    const limit = new Date(now.getTime() + days * 24 * 60 * 60 * 1000);
    
    return this.deadlines
      .filter(d => d.status === 'open')
      .filter(d => {
        const due = new Date(d.dueDate);
        return due >= now && due <= limit;
      })
      .sort((a, b) => new Date(a.dueDate) - new Date(b.dueDate));
  }

  getOverdueDeadlines() {
    const now = new Date();
    return this.deadlines
      .filter(d => d.status === 'open')
      .filter(d => new Date(d.dueDate) < now)
      .sort((a, b) => new Date(a.dueDate) - new Date(b.dueDate));
  }

  // ── Auto-Generate Tax Deadlines ──────────────────────────────
  generateTaxDeadlines(year) {
    const deadlines = [];
    
    for (const [taxType, dates] of Object.entries(TAX_DEADLINES)) {
      for (const date of dates) {
        const dueDate = new Date(year, date.month - 1, date.day);
        if (dueDate > Date.now()) {
          deadlines.push({
            type: date.type,
            description: date.description,
            dueDate: dueDate.toISOString(),
            taxType
          });
        }
      }
    }
    
    // Quarterly VAT deadlines
    for (let quarter = 1; quarter <= 4; quarter++) {
      const month = quarter * 3;
      deadlines.push({
        type: 'umsatzsteuererklärung',
        description: `USt-Voranmeldung Q${quarter}`,
        dueDate: new Date(year, month, 10).toISOString(),
        taxType: 'umsatzsteuer'
      });
    }
    
    return deadlines;
  }

  // ── Compliance Checks ────────────────────────────────────────
  async runChecks(externalData = {}) {
    const results = [];
    
    for (const rule of this.rules) {
      try {
        const check = await rule.check({ ...this.data, ...externalData });
        results.push({
          rule: rule.id,
          name: rule.name,
          severity: rule.severity,
          passed: check.passed,
          details: check.details
        });
      } catch (error) {
        results.push({
          rule: rule.id,
          name: rule.name,
          severity: rule.severity,
          passed: false,
          details: `Check failed: ${error.message}`
        });
      }
    }
    
    return results;
  }

  // ── Summary ──────────────────────────────────────────────────
  getComplianceStatus() {
    const upcoming = this.getUpcomingDeadlines(30);
    const overdue = this.getOverdueDeadlines();
    const critical = upcoming.filter(d => d.priority === 'critical');
    
    return {
      overall: overdue.length > 0 ? 'critical' : critical.length > 0 ? 'warning' : 'good',
      openDeadlines: this.deadlines.filter(d => d.status === 'open').length,
      upcoming30Days: upcoming.length,
      overdue: overdue.length,
      criticalSoon: critical.length,
      lastCheck: this.data.lastCheck
    };
  }
}

module.exports = { ComplianceEngine, TAX_DEADLINES, COMPLIANCE_RULES };

// ── CLI ─────────────────────────────────────────────────────────
if (require.main === module) {
  const engine = new ComplianceEngine();
  engine.init().then(() => {
    console.log('⚖️ Compliance Engine ready');
    console.log('Status:', engine.getComplianceStatus());
  });
}
