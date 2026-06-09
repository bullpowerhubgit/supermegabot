#!/usr/bin/env node

// 📋 TAX CORE
// Rudolf Sarkany · Tax Preparation & ELSTER Export Engine
// ===================================================

'use strict';

const fs = require('fs').promises;
const path = require('path');

const DATA_PATH = path.join(__dirname, 'tax-data.json');
const EXPORT_PATH = path.join(__dirname, 'exports');

// ── German Tax Categories (EStG / UStG) ─────────────────────────
const TAX_CATEGORIES = {
  // Einkommensteuerliche Betriebsausgaben
  'bueromiete': { type: 'betriebsausgabe', section: '4.4', description: 'Buro-Miete und Nebenkosten' },
  'software': { type: 'betriebsausgabe', section: '4.4', description: 'Software und SaaS-Lizenzen' },
  'hardware': { type: 'betriebsausgabe', section: '4.4', description: 'Computer und Peripherie' },
  'werbung': { type: 'betriebsausgabe', section: '4.4', description: 'Werbe- und Marketingkosten' },
  'reisekosten': { type: 'betriebsausgabe', section: '4.5', description: 'Reise- und Fahrtkosten' },
  'bewirtung': { type: 'betriebsausgabe', section: '4.5', description: 'Bewirtungskosten (70%)' },
  'weiterbildung': { type: 'betriebsausgabe', section: '4.4', description: 'Fortbildungskosten' },
  'versicherung': { type: 'betriebsausgabe', section: '4.4', description: 'Betriebliche Versicherungen' },
  'telekommunikation': { type: 'betriebsausgabe', section: '4.4', description: 'Telefon und Internet' },
  'bankgebuehren': { type: 'betriebsausgabe', section: '4.4', description: 'Bank- und Transaktionsgebuhren' },
  
  // Umsatzsteuer
  'umsatzsteuer': { type: 'ust', section: 'UStG', description: 'Umsatzsteuer' },
  'vorsteuer': { type: 'ust', section: 'UStG', description: 'Vorsteuer aus Rechnungen' },
  
  // Private Ausgaben (nicht absetzbar)
  'privat': { type: 'privat', section: '-', description: 'Private Ausgaben' },
  'freizeit': { type: 'privat', section: '-', description: 'Freizeit und Unterhaltung' }
};

// ── Tax Core ────────────────────────────────────────────────────
class TaxCore {
  constructor() {
    this.taxData = {};
    this.fiscalYear = new Date().getFullYear();
  }

  async init() {
    try {
      await fs.mkdir(EXPORT_PATH, { recursive: true });
      const data = await fs.readFile(DATA_PATH, 'utf8');
      this.taxData = JSON.parse(data);
      console.log('📋 Tax Core initialized');
    } catch (error) {
      console.log('📋 Tax Core initialized (empty)');
    }
  }

  async save() {
    await fs.writeFile(DATA_PATH, JSON.stringify(this.taxData, null, 2), 'utf8');
  }

  // ── Document Management ────────────────────────────────────────
  async addDocument(doc) {
    const document = {
      id: crypto.randomUUID(),
      type: doc.type || 'receipt',
      date: doc.date || new Date().toISOString(),
      description: doc.description,
      amount: parseFloat(doc.amount),
      category: doc.category || 'unbekannt',
      taxCategory: TAX_CATEGORIES[doc.category] || TAX_CATEGORIES['privat'],
      vendor: doc.vendor,
      invoiceNumber: doc.invoiceNumber,
      vatRate: doc.vatRate || 19,
      vatAmount: doc.vatAmount || (doc.amount * 0.19),
      netAmount: doc.netAmount || (doc.amount / 1.19),
      files: doc.files || [],
      tags: doc.tags || [],
      status: 'pending',
      created: new Date().toISOString()
    };
    
    if (!this.taxData.documents) this.taxData.documents = [];
    this.taxData.documents.push(document);
    await this.save();
    
    return document;
  }

  // ── Tax Calculation ──────────────────────────────────────────
  calculateIncomeTax(taxableIncome) {
    // Grundfreibetrag 2025
    const grundfreibetrag = 12084;
    
    if (taxableIncome <= grundfreibetrag) return 0;
    
    const zuVersteuerndesEinkommen = taxableIncome - grundfreibetrag;
    
    // Einkommensteuertarif 2025 (progressiv)
    let steuer = 0;
    if (zuVersteuerndesEinkommen <= 11784) {
      steuer = (zuVersteuerndesEinkommen * 0.14) / 11784;
    } else if (zuVersteuerndesEinkommen <= 17749) {
      const y = (zuVersteuerndesEinkommen - 11784) / 10000;
      steuer = (226.26 * y + 2397) * y + 1030;
    } else if (zuVersteuerndesEinkommen <= 34814) {
      const z = (zuVersteuerndesEinkommen - 17749) / 10000;
      steuer = (389.91 * z + 2220.65) * z + 1030;
    } else if (zuVersteuerndesEinkommen <= 60216) {
      steuer = 0.42 * zuVersteuerndesEinkommen - 10640;
    } else {
      steuer = 0.45 * zuVersteuerndesEinkommen - 17940;
    }
    
    return Math.round(steuer * 100) / 100;
  }

  calculateUSt(turnover, inputTax) {
    const ustRate = 0.19; // Regelsteuersatz
    const ust = turnover * ustRate;
    const payable = ust - inputTax;
    
    return {
      turnover,
      ustRate: 19,
      ustAmount: Math.round(ust * 100) / 100,
      inputTax: Math.round(inputTax * 100) / 100,
      payable: Math.round(payable * 100) / 100
    };
  }

  // ── Export Functions ────────────────────────────────────────
  async exportELSTER(year) {
    const docs = (this.taxData.documents || []).filter(d => {
      const dYear = new Date(d.date).getFullYear();
      return dYear === year && d.status !== 'rejected';
    });
    
    const einkuenfte = {};
    const betriebsausgaben = {};
    let totalEinkuenfte = 0;
    let totalAusgaben = 0;
    
    for (const doc of docs) {
      if (doc.taxCategory.type === 'betriebsausgabe') {
        betriebsausgaben[doc.category] = (betriebsausgaben[doc.category] || 0) + doc.amount;
        totalAusgaben += doc.amount;
      }
    }
    
    const exportData = {
      year,
      generated: new Date().toISOString(),
      anlageE: {
        einkuenfte: totalEinkuenfte,
        werbungskosten: totalAusgaben,
        zuVersteuerndesEinkommen: totalEinkuenfte - totalAusgaben
      },
      betriebsausgaben: Object.entries(betriebsausgaben).map(([cat, amount]) => ({
        category: cat,
        amount,
        description: TAX_CATEGORIES[cat]?.description || 'Sonstige'
      })),
      documents: docs.map(d => ({
        id: d.id,
        date: d.date,
        description: d.description,
        amount: d.amount,
        category: d.category
      }))
    };
    
    const filename = `ELSTER-export-${year}.json`;
    await fs.writeFile(
      path.join(EXPORT_PATH, filename),
      JSON.stringify(exportData, null, 2),
      'utf8'
    );
    
    return { filename, path: path.join(EXPORT_PATH, filename), data: exportData };
  }

  async exportCSV(year) {
    const docs = (this.taxData.documents || []).filter(d => {
      const dYear = new Date(d.date).getFullYear();
      return dYear === year;
    });
    
    const headers = ['Datum', 'Bezeichnung', 'Kategorie', 'Betrag', 'MwSt', 'Netto', 'Dokument'];
    const rows = docs.map(d => [
      d.date.split('T')[0],
      `"${d.description}"`,
      d.category,
      d.amount.toFixed(2),
      d.vatAmount.toFixed(2),
      d.netAmount.toFixed(2),
      d.invoiceNumber || ''
    ]);
    
    const csv = [headers.join(';'), ...rows.map(r => r.join(';'))].join('\n');
    
    const filename = `tax-export-${year}.csv`;
    await fs.writeFile(path.join(EXPORT_PATH, filename), csv, 'utf8');
    
    return { filename, path: path.join(EXPORT_PATH, filename) };
  }

  // ── Summary ──────────────────────────────────────────────────
  getYearSummary(year) {
    const docs = (this.taxData.documents || []).filter(d => {
      return new Date(d.date).getFullYear() === year;
    });
    
    const totalExpenses = docs
      .filter(d => d.taxCategory?.type === 'betriebsausgabe')
      .reduce((sum, d) => sum + d.amount, 0);
    
    const byCategory = {};
    for (const d of docs) {
      if (d.taxCategory?.type === 'betriebsausgabe') {
        byCategory[d.category] = (byCategory[d.category] || 0) + d.amount;
      }
    }
    
    return {
      year,
      totalDocuments: docs.length,
      totalExpenses,
      categories: Object.entries(byCategory)
        .map(([cat, amount]) => ({ category: cat, amount }))
        .sort((a, b) => b.amount - a.amount)
    };
  }
}

module.exports = { TaxCore, TAX_CATEGORIES };

// ── CLI ─────────────────────────────────────────────────────────
if (require.main === module) {
  const taxCore = new TaxCore();
  taxCore.init().then(() => {
    console.log('📋 Tax Core ready');
  });
}
